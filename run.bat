@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1
title ximagine-2api - Smart Launcher

:: ==========================================
:: ximagine-2api Python Edition - Smart Launcher
:: Features:
::   - Auto-detect / download Python
::   - Auto-create virtual environment
::   - Live dependency installation log
::   - Fast-launch mode (Marker File)
:: ==========================================

cd /d "%~dp0"

:: Configuration
set "APP_NAME=ximagine-2api Video Generation Service"
set "PYTHON_VERSION=3.11.9"
set "PYTHON_DIR=%~dp0python"
set "VENV_DIR=%~dp0venv"
set "MARKER_FILE=%~dp0.env_ready"
set "PYTHON_URL=https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip"
set "GET_PIP_URL=https://bootstrap.pypa.io/get-pip.py"

:: Show header
echo.
echo ==========================================
echo    %APP_NAME% - Smart Launcher
echo ==========================================
echo.

:: Fast check - if marker file exists, skip full check
if exist "%MARKER_FILE%" (
    echo [*] Fast Mode: Environment was already verified
    echo.
    goto :run_app
)

echo [*] First run or environment needs checking...
echo.

:: ==========================================
:: Step 1: Check Python environment
:: ==========================================
echo [1/4] Checking Python environment...

set "PYTHON_EXE="
set "USE_EMBEDDED=0"

:: Priority 1: Check for embedded Python
if exist "%PYTHON_DIR%\python.exe" (
    set "PYTHON_EXE=%PYTHON_DIR%\python.exe"
    set "USE_EMBEDDED=1"
    echo      [+] Found embedded Python
    goto :python_found
)

:: Priority 2: Check for system Python
where python >nul 2>&1
if %errorlevel% equ 0 (
    for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set "SYSTEM_PY_VER=%%v"
    echo      [+] Found system Python: !SYSTEM_PY_VER!

    :: Check version >= 3.8
    for /f "tokens=1,2 delims=." %%a in ("!SYSTEM_PY_VER!") do (
        if %%a geq 3 if %%b geq 8 (
            set "PYTHON_EXE=python"
            echo      [+] Version meets requirements, using system Python
            goto :python_found
        )
    )
    echo      [-] Version too old, Python 3.8+ is required
)

:: No suitable Python found, download embedded version
echo      [-] No suitable Python found, downloading embedded version...
goto :download_python

:python_found
echo      [OK] Python environment ready
echo.
goto :check_venv

:: ==========================================
:: Step 2: Download embedded Python
:: ==========================================
:download_python
echo.
echo [*] Downloading Python %PYTHON_VERSION% embedded edition...
echo     URL: %PYTHON_URL%
echo.

:: Create python directory
if not exist "%PYTHON_DIR%" mkdir "%PYTHON_DIR%"

:: Use PowerShell to download (with progress)
set "PYTHON_ZIP=%PYTHON_DIR%\python.zip"
echo     Downloading...
powershell -Command "& {$ProgressPreference = 'Continue'; [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%PYTHON_URL%' -OutFile '%PYTHON_ZIP%' -UseBasicParsing}"

if not exist "%PYTHON_ZIP%" (
    echo.
    echo [Error] Python download failed. Please check your network connection.
    echo         You can manually install Python 3.8+ and try again.
    pause
    exit /b 1
)

:: Extract
echo     Extracting...
powershell -Command "& {Expand-Archive -Path '%PYTHON_ZIP%' -DestinationPath '%PYTHON_DIR%' -Force}"
del "%PYTHON_ZIP%" 2>nul

:: Enable pip support - modify python311._pth
set "PTH_FILE=%PYTHON_DIR%\python311._pth"
if exist "%PTH_FILE%" (
    echo python311.zip> "%PTH_FILE%"
    echo .>> "%PTH_FILE%"
    echo Lib\site-packages>> "%PTH_FILE%"
    echo import site>> "%PTH_FILE%"
)

:: Download and install pip
echo.
echo [*] Installing pip...
set "GET_PIP=%PYTHON_DIR%\get-pip.py"
powershell -Command "& {$ProgressPreference = 'Continue'; [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%GET_PIP_URL%' -OutFile '%GET_PIP%' -UseBasicParsing}"

"%PYTHON_DIR%\python.exe" "%GET_PIP%"
del "%GET_PIP%" 2>nul

set "PYTHON_EXE=%PYTHON_DIR%\python.exe"
set "USE_EMBEDDED=1"
echo      [OK] Embedded Python installed successfully
echo.

:: ==========================================
:: Step 3: Check / create virtual environment
:: ==========================================
:check_venv
echo [2/4] Checking virtual environment...

:: For embedded Python, skip venv (use embedded environment directly)
if "%USE_EMBEDDED%"=="1" (
    echo      [+] Using embedded Python, skipping virtual environment creation
    set "PIP_EXE=%PYTHON_DIR%\Scripts\pip.exe"
    if not exist "!PIP_EXE!" set "PIP_EXE=%PYTHON_DIR%\python.exe -m pip"
    echo.
    goto :check_deps
)

:: Check if venv already exists
if exist "%VENV_DIR%\Scripts\python.exe" (
    echo      [OK] Virtual environment already exists
    set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"
    set "PIP_EXE=%VENV_DIR%\Scripts\pip.exe"
    echo.
    goto :check_deps
)

:: Create virtual environment
echo      [+] Creating virtual environment...
python -m venv "%VENV_DIR%"
if %errorlevel% neq 0 (
    echo [Error] Failed to create virtual environment
    pause
    exit /b 1
)

set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"
set "PIP_EXE=%VENV_DIR%\Scripts\pip.exe"
echo      [OK] Virtual environment created successfully
echo.

:: ==========================================
:: Step 4: Check / install dependencies
:: ==========================================
:check_deps
echo [3/4] Checking dependencies...

:: Quick check - try importing key modules
"%PYTHON_EXE%" -c "import flask; import flask_cors; import requests; import webview; import cryptography" 2>nul
if %errorlevel% equ 0 (
    echo      [OK] All dependencies are installed
    echo.
    goto :create_marker
)

:: Install missing dependencies (show full output for visibility)
echo.
echo      [-] Missing dependencies found, installing...
echo      ============================================
echo.

if "%USE_EMBEDDED%"=="1" (
    echo [pip] Installing from requirements.txt...
    "%PYTHON_EXE%" -m pip install -r requirements.txt --no-warn-script-location
) else (
    echo [pip] Installing from requirements.txt...
    "%PIP_EXE%" install -r requirements.txt
)

echo.
if %errorlevel% neq 0 (
    echo [Error] Some dependencies failed to install.
    echo         Please check your network connection or try switching your PyPI mirror.
    pause
    exit /b 1
)
echo      ============================================
echo      [OK] Dependencies installed successfully!
echo.

:: ==========================================
:: Step 5: Create marker file
:: ==========================================
:create_marker
echo [4/4] Finishing setup...

:: Create timestamped marker file
echo Environment validated on %date% %time%> "%MARKER_FILE%"
echo Python: %PYTHON_EXE%>> "%MARKER_FILE%"
echo      [OK] Environment is ready
echo.

:: ==========================================
:: Run the application
:: ==========================================
:run_app
echo ==========================================
echo    Starting ximagine-2api service...
echo    Service address: http://127.0.0.1:5000
echo    Do NOT close this window
echo ==========================================
echo.

:: Confirm Python executable path (re-check as a safety measure)
if exist "%VENV_DIR%\Scripts\python.exe" (
    set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"
) else if exist "%PYTHON_DIR%\python.exe" (
    set "PYTHON_EXE=%PYTHON_DIR%\python.exe"
) else (
    set "PYTHON_EXE=python"
)

:: Run main program
"%PYTHON_EXE%" main.py

if %errorlevel% neq 0 (
    echo.
    echo [Error] Application exited with an error. Error code: %errorlevel%
    echo.
    :: Delete marker file to force a full re-check on next run
    del "%MARKER_FILE%" 2>nul
    pause
)

endlocal