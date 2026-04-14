@echo off
REM ===================================================================
REM  TPRM_AI - pgvector Installation Script (Run as Administrator)
REM  
REM  This script:
REM  1. Installs Visual Studio Build Tools (C++ workload)
REM  2. Downloads pgvector source
REM  3. Compiles and installs pgvector extension into PostgreSQL 18
REM  4. Creates the vector extension in the tprm_db database
REM ===================================================================

echo ===================================================================
echo   TPRM_AI - pgvector Setup (Run As Administrator!)
echo ===================================================================
echo.

REM Check for admin rights
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: This script must be run as Administrator!
    echo Right-click this file and select "Run as administrator".
    pause
    exit /b 1
)

set PG_DIR=C:\Program Files\PostgreSQL\18
set PSQL="%PG_DIR%\bin\psql.exe"
set PG_CONFIG="%PG_DIR%\bin\pg_config.exe"

REM ---- Step 1: Install Visual Studio Build Tools ----
echo [Step 1/4] Checking for Visual Studio Build Tools...

where cl >nul 2>&1
if %errorlevel% neq 0 (
    echo Installing Visual Studio 2022 Build Tools...
    echo This may take 10-20 minutes. Please wait...
    winget install --id Microsoft.VisualStudio.2022.BuildTools --accept-package-agreements --accept-source-agreements --override "--passive --wait --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"
    if %errorlevel% neq 0 (
        echo.
        echo WARNING: winget install may have failed. Attempting manual download...
        echo Downloading VS Build Tools installer...
        powershell -Command "Invoke-WebRequest -Uri 'https://aka.ms/vs/17/release/vs_BuildTools.exe' -OutFile '%TEMP%\vs_BuildTools.exe'"
        echo Running installer...
        "%TEMP%\vs_BuildTools.exe" --passive --wait --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended
    )
    echo Build Tools installation complete.
) else (
    echo Visual Studio Build Tools already available.
)

REM ---- Step 2: Set up MSVC environment ----
echo [Step 2/4] Setting up MSVC environment...

REM Find vcvarsall.bat
set VCVARS=
for /f "tokens=*" %%i in ('"%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath 2^>nul') do set VSINSTALL=%%i

if defined VSINSTALL (
    set "VCVARS=%VSINSTALL%\VC\Auxiliary\Build\vcvarsall.bat"
) else (
    echo ERROR: Cannot find Visual Studio installation.
    echo Please install Visual Studio Build Tools manually and re-run.
    pause
    exit /b 1
)

if not exist "%VCVARS%" (
    echo ERROR: vcvarsall.bat not found at %VCVARS%
    pause
    exit /b 1
)

call "%VCVARS%" x64

REM ---- Step 3: Download and build pgvector ----
echo [Step 3/4] Downloading and building pgvector...

set BUILD_DIR=%TEMP%\pgvector-build
if exist "%BUILD_DIR%" rmdir /s /q "%BUILD_DIR%"
mkdir "%BUILD_DIR%"
cd /d "%BUILD_DIR%"

echo Downloading pgvector source...
powershell -Command "Invoke-WebRequest -Uri 'https://github.com/pgvector/pgvector/archive/refs/tags/v0.8.0.zip' -OutFile 'pgvector.zip'"
if %errorlevel% neq 0 (
    echo ERROR: Failed to download pgvector source.
    pause
    exit /b 1
)

echo Extracting...
powershell -Command "Expand-Archive -Path 'pgvector.zip' -DestinationPath '.' -Force"

cd pgvector-0.8.0

echo Building pgvector...
set "PG_CONFIG_PATH=%PG_DIR%\bin\pg_config.exe"
nmake /F Makefile.win PG_CONFIG="%PG_CONFIG_PATH%"
if %errorlevel% neq 0 (
    echo ERROR: pgvector build failed.
    pause
    exit /b 1
)

echo Installing pgvector into PostgreSQL...
nmake /F Makefile.win install PG_CONFIG="%PG_CONFIG_PATH%"
if %errorlevel% neq 0 (
    echo ERROR: pgvector install failed.
    pause
    exit /b 1
)

echo pgvector installed successfully!

REM ---- Step 4: Create extension in database ----
echo [Step 4/4] Creating vector extension in tprm_db...

set PGPASSWORD=Bro2228jp@
%PSQL% -U postgres -h 127.0.0.1 -d tprm_db -c "CREATE EXTENSION IF NOT EXISTS vector"
if %errorlevel% neq 0 (
    echo WARNING: Could not create vector extension. You may need to create it manually:
    echo   psql -U postgres -d tprm_db -c "CREATE EXTENSION IF NOT EXISTS vector"
) else (
    echo Vector extension created successfully!
)

echo.
echo ===================================================================
echo   pgvector installation complete!
echo   You can now run: alembic upgrade head
echo ===================================================================
pause
