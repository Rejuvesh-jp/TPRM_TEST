@echo off
REM ============================================================
REM TPRM_AI - pgvector Installer for Windows (Run as Administrator)
REM ============================================================
REM Right-click this file and select "Run as administrator"
REM ============================================================

echo ============================================================
echo  TPRM_AI - pgvector Extension Installer
echo ============================================================
echo.

REM Step 1: Check if Build Tools are already installed
set "VCVARSALL="
for %%v in (2022 2019) do (
    for %%e in (BuildTools Community Professional Enterprise) do (
        if exist "C:\Program Files\Microsoft Visual Studio\%%v\%%e\VC\Auxiliary\Build\vcvarsall.bat" (
            set "VCVARSALL=C:\Program Files\Microsoft Visual Studio\%%v\%%e\VC\Auxiliary\Build\vcvarsall.bat"
            echo Found Visual Studio at: C:\Program Files\Microsoft Visual Studio\%%v\%%e
            goto :found_vs
        )
        if exist "C:\Program Files (x86)\Microsoft Visual Studio\%%v\%%e\VC\Auxiliary\Build\vcvarsall.bat" (
            set "VCVARSALL=C:\Program Files (x86)\Microsoft Visual Studio\%%v\%%e\VC\Auxiliary\Build\vcvarsall.bat"
            echo Found Visual Studio at: C:\Program Files (x86)\Microsoft Visual Studio\%%v\%%e
            goto :found_vs
        )
    )
)

echo Visual Studio Build Tools not found. Installing...
echo.
echo This will download and install Visual Studio 2022 Build Tools (~2GB).
echo Please wait, this may take several minutes...
echo.

winget install --id Microsoft.VisualStudio.2022.BuildTools --source winget --override "--passive --wait --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended" --accept-package-agreements --accept-source-agreements --disable-interactivity

REM Re-check after installation
for %%v in (2022 2019) do (
    for %%e in (BuildTools Community Professional Enterprise) do (
        if exist "C:\Program Files\Microsoft Visual Studio\%%v\%%e\VC\Auxiliary\Build\vcvarsall.bat" (
            set "VCVARSALL=C:\Program Files\Microsoft Visual Studio\%%v\%%e\VC\Auxiliary\Build\vcvarsall.bat"
            goto :found_vs
        )
        if exist "C:\Program Files (x86)\Microsoft Visual Studio\%%v\%%e\VC\Auxiliary\Build\vcvarsall.bat" (
            set "VCVARSALL=C:\Program Files (x86)\Microsoft Visual Studio\%%v\%%e\VC\Auxiliary\Build\vcvarsall.bat"
            goto :found_vs
        )
    )
)

echo ERROR: Visual Studio Build Tools installation failed.
echo Please install manually from: https://visualstudio.microsoft.com/visual-cpp-build-tools/
echo Select "Desktop development with C++" workload.
pause
exit /b 1

:found_vs
echo Using: %VCVARSALL%
echo.

REM Step 2: Set up MSVC environment
echo Setting up build environment...
call "%VCVARSALL%" x64
if errorlevel 1 (
    echo ERROR: Failed to set up build environment.
    pause
    exit /b 1
)

REM Step 3: Set PostgreSQL root
set "PGROOT=C:\Program Files\PostgreSQL\18"
if not exist "%PGROOT%\bin\pg_config.exe" (
    echo ERROR: PostgreSQL 18 not found at %PGROOT%
    echo Please edit this script and set PGROOT to your PostgreSQL installation path.
    pause
    exit /b 1
)
echo PostgreSQL found at: %PGROOT%

REM Step 4: Clone pgvector
echo.
echo Cloning pgvector v0.8.2...
cd /d %TEMP%
if exist pgvector (
    echo Removing old pgvector directory...
    rmdir /s /q pgvector
)
git clone --branch v0.8.2 https://github.com/pgvector/pgvector.git
if errorlevel 1 (
    echo ERROR: Failed to clone pgvector. Make sure git is installed.
    pause
    exit /b 1
)
cd pgvector

REM Step 5: Build pgvector
echo.
echo Building pgvector...
nmake /F Makefile.win
if errorlevel 1 (
    echo ERROR: Build failed.
    pause
    exit /b 1
)

REM Step 6: Install pgvector
echo.
echo Installing pgvector into PostgreSQL...
nmake /F Makefile.win install
if errorlevel 1 (
    echo ERROR: Installation failed. Make sure you are running as administrator.
    pause
    exit /b 1
)

REM Step 7: Verify installation
echo.
echo ============================================================
echo  pgvector installed successfully!
echo ============================================================
echo.
echo Now run this SQL command in psql or pgAdmin to enable it:
echo   CREATE EXTENSION vector;
echo.
echo Verifying files...
if exist "%PGROOT%\share\extension\vector.control" (
    echo   [OK] vector.control found
) else (
    echo   [FAIL] vector.control not found
)
if exist "%PGROOT%\lib\vector.dll" (
    echo   [OK] vector.dll found
) else (
    echo   [FAIL] vector.dll not found
)

echo.
pause
