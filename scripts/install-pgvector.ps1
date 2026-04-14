# ============================================================
# TPRM_AI - pgvector Auto-Installer (Self-Elevating)
# ============================================================
# Double-click this file OR right-click -> "Run with PowerShell"
# It will automatically request admin rights.
# ============================================================

# Self-elevate if not running as admin
if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "Requesting administrator privileges..." -ForegroundColor Yellow
    Start-Process -FilePath "powershell.exe" -ArgumentList "-ExecutionPolicy Bypass -File `"$PSCommandPath`"" -Verb RunAs
    exit
}

$ErrorActionPreference = "Stop"
$PGROOT = "C:\Program Files\PostgreSQL\18"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  TPRM_AI - pgvector Extension Installer" -ForegroundColor Cyan
Write-Host "  Running as Administrator" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# -----------------------------------------------------------
# Step 1: Verify PostgreSQL
# -----------------------------------------------------------
Write-Host "[1/6] Checking PostgreSQL..." -ForegroundColor Yellow
if (-not (Test-Path "$PGROOT\bin\pg_config.exe")) {
    Write-Host "  ERROR: PostgreSQL 18 not found at $PGROOT" -ForegroundColor Red
    Write-Host "  Please edit PGROOT variable in this script." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}
$pgVersion = & "$PGROOT\bin\pg_config.exe" --version
Write-Host "  OK: $pgVersion" -ForegroundColor Green

# -----------------------------------------------------------
# Step 2: Check/Install Visual Studio Build Tools
# -----------------------------------------------------------
Write-Host ""
Write-Host "[2/6] Checking C++ Build Tools..." -ForegroundColor Yellow

$vcvarsall = $null
$searchPaths = @(
    "C:\Program Files\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvarsall.bat",
    "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat",
    "C:\Program Files\Microsoft Visual Studio\2022\Professional\VC\Auxiliary\Build\vcvarsall.bat",
    "C:\Program Files\Microsoft Visual Studio\2022\Enterprise\VC\Auxiliary\Build\vcvarsall.bat",
    "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvarsall.bat",
    "C:\Program Files (x86)\Microsoft Visual Studio\2019\BuildTools\VC\Auxiliary\Build\vcvarsall.bat",
    "C:\Program Files (x86)\Microsoft Visual Studio\2019\Community\VC\Auxiliary\Build\vcvarsall.bat"
)

foreach ($path in $searchPaths) {
    if (Test-Path $path) {
        $vcvarsall = $path
        break
    }
}

if (-not $vcvarsall) {
    Write-Host "  C++ Build Tools not found. Installing VS 2022 Build Tools..." -ForegroundColor Yellow
    Write-Host "  This downloads ~2GB and may take several minutes..." -ForegroundColor Yellow
    Write-Host ""
    
    $wingetAvailable = Get-Command winget -ErrorAction SilentlyContinue
    if ($wingetAvailable) {
        & winget install --id Microsoft.VisualStudio.2022.BuildTools --source winget `
            --override "--passive --wait --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended" `
            --accept-package-agreements --accept-source-agreements --disable-interactivity
    } else {
        Write-Host "  winget not available. Downloading installer directly..." -ForegroundColor Yellow
        $installerUrl = "https://aka.ms/vs/17/release/vs_buildtools.exe"
        $installerPath = "$env:TEMP\vs_buildtools.exe"
        Invoke-WebRequest -Uri $installerUrl -OutFile $installerPath
        Start-Process -FilePath $installerPath -ArgumentList "--passive --wait --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended" -Wait
    }
    
    # Re-check
    foreach ($path in $searchPaths) {
        if (Test-Path $path) {
            $vcvarsall = $path
            break
        }
    }
    
    if (-not $vcvarsall) {
        Write-Host "  ERROR: Build Tools installation failed." -ForegroundColor Red
        Write-Host "  Please install manually from: https://visualstudio.microsoft.com/visual-cpp-build-tools/" -ForegroundColor Red
        Write-Host "  Select 'Desktop development with C++' workload." -ForegroundColor Red
        Read-Host "Press Enter to exit"
        exit 1
    }
}

Write-Host "  OK: Found Build Tools" -ForegroundColor Green
Write-Host "  $vcvarsall" -ForegroundColor DarkGray

# -----------------------------------------------------------
# Step 3: Clone pgvector
# -----------------------------------------------------------
Write-Host ""
Write-Host "[3/6] Downloading pgvector v0.8.2..." -ForegroundColor Yellow

$buildDir = "$env:TEMP\pgvector-build"
if (Test-Path $buildDir) { Remove-Item $buildDir -Recurse -Force }
New-Item -ItemType Directory -Path $buildDir -Force | Out-Null

$gitAvailable = Get-Command git -ErrorAction SilentlyContinue
if ($gitAvailable) {
    & git clone --branch v0.8.2 https://github.com/pgvector/pgvector.git "$buildDir\pgvector" 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  ERROR: git clone failed" -ForegroundColor Red
        Read-Host "Press Enter to exit"
        exit 1
    }
} else {
    Write-Host "  git not found. Downloading ZIP..." -ForegroundColor Yellow
    $zipUrl = "https://github.com/pgvector/pgvector/archive/refs/tags/v0.8.2.zip"
    $zipPath = "$buildDir\pgvector.zip"
    Invoke-WebRequest -Uri $zipUrl -OutFile $zipPath
    Expand-Archive -Path $zipPath -DestinationPath $buildDir
    Rename-Item "$buildDir\pgvector-0.8.2" "$buildDir\pgvector"
}
Write-Host "  OK: pgvector source downloaded" -ForegroundColor Green

# -----------------------------------------------------------
# Step 4: Build pgvector
# -----------------------------------------------------------
Write-Host ""
Write-Host "[4/6] Building pgvector..." -ForegroundColor Yellow

# Create a build script that sets up MSVC environment and builds
$buildScript = @"
@echo off
call "$vcvarsall" x64
if errorlevel 1 exit /b 1
set "PGROOT=$PGROOT"
cd /d "$buildDir\pgvector"
nmake /F Makefile.win
if errorlevel 1 exit /b 2
nmake /F Makefile.win install
if errorlevel 1 exit /b 3
echo BUILD_SUCCESS
"@

$buildScriptPath = "$buildDir\build.bat"
Set-Content -Path $buildScriptPath -Value $buildScript -Encoding ASCII

$buildProcess = Start-Process -FilePath "cmd.exe" -ArgumentList "/c `"$buildScriptPath`"" -Wait -PassThru -NoNewWindow
if ($buildProcess.ExitCode -ne 0) {
    Write-Host "  ERROR: Build failed with exit code $($buildProcess.ExitCode)" -ForegroundColor Red
    switch ($buildProcess.ExitCode) {
        1 { Write-Host "  Failed to set up MSVC environment" -ForegroundColor Red }
        2 { Write-Host "  Compilation failed" -ForegroundColor Red }
        3 { Write-Host "  Installation failed (file copy)" -ForegroundColor Red }
    }
    Read-Host "Press Enter to exit"
    exit 1
}
Write-Host "  OK: pgvector built and installed" -ForegroundColor Green

# -----------------------------------------------------------
# Step 5: Verify installation files
# -----------------------------------------------------------
Write-Host ""
Write-Host "[5/6] Verifying installation files..." -ForegroundColor Yellow

$controlOk = Test-Path "$PGROOT\share\extension\vector.control"
$dllOk = Test-Path "$PGROOT\lib\vector.dll"

if ($controlOk) { Write-Host "  OK: vector.control" -ForegroundColor Green }
else { Write-Host "  MISSING: vector.control" -ForegroundColor Red }

if ($dllOk) { Write-Host "  OK: vector.dll" -ForegroundColor Green }
else { Write-Host "  MISSING: vector.dll" -ForegroundColor Red }

$sqlFiles = Get-ChildItem "$PGROOT\share\extension\vector--*.sql" -ErrorAction SilentlyContinue
Write-Host "  SQL files: $($sqlFiles.Count) found" -ForegroundColor $(if ($sqlFiles.Count -gt 0) { "Green" } else { "Red" })

if (-not ($controlOk -and $dllOk)) {
    Write-Host ""
    Write-Host "  ERROR: Some files are missing. Installation may have failed." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

# -----------------------------------------------------------
# Step 6: Enable extension in PostgreSQL
# -----------------------------------------------------------
Write-Host ""
Write-Host "[6/6] Enabling pgvector extension..." -ForegroundColor Yellow

# Check if extension is now available
$env:PGPASSWORD = "Bro2228jp@"
$result = & "$PGROOT\bin\psql.exe" -U postgres -h 127.0.0.1 -p 5432 -c "SELECT name, default_version FROM pg_available_extensions WHERE name='vector';" 2>&1
if ($result -match "vector") {
    Write-Host "  OK: pgvector is available in PostgreSQL" -ForegroundColor Green
    
    # Create database if not exists
    $dbCheck = & "$PGROOT\bin\psql.exe" -U postgres -h 127.0.0.1 -p 5432 -c "SELECT 1 FROM pg_database WHERE datname='tprm_db';" 2>&1
    if ($dbCheck -notmatch "1") {
        Write-Host "  Creating database tprm_db..." -ForegroundColor Yellow
        & "$PGROOT\bin\psql.exe" -U postgres -h 127.0.0.1 -p 5432 -c "CREATE DATABASE tprm_db;" 2>&1 | Out-Null
    }
    
    # Enable extension in tprm_db
    $extResult = & "$PGROOT\bin\psql.exe" -U postgres -h 127.0.0.1 -p 5432 -d tprm_db -c "CREATE EXTENSION IF NOT EXISTS vector;" 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  OK: pgvector extension enabled in tprm_db" -ForegroundColor Green
    } else {
        Write-Host "  Note: Extension available but could not auto-enable. Run manually:" -ForegroundColor Yellow
        Write-Host "  CREATE EXTENSION IF NOT EXISTS vector;" -ForegroundColor White
    }
    
    # Verify
    $verifyResult = & "$PGROOT\bin\psql.exe" -U postgres -h 127.0.0.1 -p 5432 -d tprm_db -c "SELECT extname, extversion FROM pg_extension WHERE extname='vector';" 2>&1
    Write-Host ""
    Write-Host $verifyResult
} else {
    Write-Host "  WARNING: Extension files installed but PostgreSQL doesn't see them." -ForegroundColor Yellow  
    Write-Host "  You may need to restart the PostgreSQL service." -ForegroundColor Yellow
    Write-Host "  Then run: CREATE EXTENSION vector;" -ForegroundColor White
}

# Cleanup
Remove-Item $env:PGPASSWORD -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Installation Complete!" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Read-Host "Press Enter to close"
