@echo off
setlocal
chcp 65001 >nul 2>&1
set "PYTHONIOENCODING=utf-8"

REM PC Temperature Monitor - one-click launcher (start.bat)
REM
REM Pure ASCII on purpose: cmd.exe parses the .bat file using the system
REM codepage (CP936/CP1252) at STARTUP, before any line runs. chcp 65001
REM only affects output, not how the script itself is parsed. Putting
REM Chinese / non-ASCII bytes in this file would corrupt the parser.
REM
REM venv is based on E:\Python312\python.exe (clean CPython 3.12.9).
REM To recreate: rmdir /s /q venv, then E:\Python312\python.exe -m venv venv

set "ROOT=%~dp0"
pushd "%ROOT%"

set "PYTHON_EXE=py -3.12"
%PYTHON_EXE% --version >nul 2>&1
if errorlevel 1 (
    set "PYTHON_EXE=python"
)

call "venv\Scripts\activate.bat"

echo [start.bat] Installing requirements (idempotent)...
python -m pip install --upgrade pip >nul 2>&1
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo [start.bat] pip install failed. Aborting.
    popd
    exit /b 1
)

if "%1"=="--smoke" goto smoke

REM --- Ensure LibreHardwareMonitor is running -----------------------
REM LHM_PATH_OVERRIDE can override the default. Without it we look in
REM the user's current install location, then a few common paths.
set "LHM_PATH="
if not "%LHM_PATH_OVERRIDE%"=="" set "LHM_PATH=%LHM_PATH_OVERRIDE%"
if "%LHM_PATH%"=="" (
    if exist "D:\code\AI\tools\LibreHardwareMonitor.NET.10\LibreHardwareMonitor.exe" set "LHM_PATH=D:\code\AI\tools\LibreHardwareMonitor.NET.10\LibreHardwareMonitor.exe"
)
if "%LHM_PATH%"=="" (
    if exist "C:\Program Files\LibreHardwareMonitor\LibreHardwareMonitor.exe" set "LHM_PATH=C:\Program Files\LibreHardwareMonitor\LibreHardwareMonitor.exe"
)
if "%LHM_PATH%"=="" (
    if exist "C:\LibreHardwareMonitor\LibreHardwareMonitor.exe" set "LHM_PATH=C:\LibreHardwareMonitor\LibreHardwareMonitor.exe"
)

if "%LHM_PATH%"=="" goto lhm_skip
REM LHM is found. Check if already running.
tasklist /FI "IMAGENAME eq LibreHardwareMonitor.exe" 2>nul | find /I "LibreHardwareMonitor.exe" >nul
if not errorlevel 1 goto lhm_already
echo [start.bat] Starting LibreHardwareMonitor: %LHM_PATH%
start "" /B "%LHM_PATH%"
echo [start.bat] Waiting for LHM HTTP server (port 8085)...
set LHM_WAIT=0
:lhm_poll
powershell -NoProfile -Command "try { (Invoke-WebRequest 'http://127.0.0.1:8085/' -UseBasicParsing -TimeoutSec 1).StatusCode } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 goto lhm_ready
set /a LHM_WAIT=LHM_WAIT+1
if %LHM_WAIT% GEQ 8 goto lhm_ready
timeout /t 1 /nobreak >nul 2>&1
goto lhm_poll
:lhm_ready
if %LHM_WAIT% GEQ 8 (
    echo [start.bat] LHM HTTP server not detected after 8s. Continuing anyway.
    echo [start.bat] If sensors stay N/A, open LHM and check the Remote Web Server option.
) else (
    echo [start.bat] LHM HTTP server ready.
)
goto lhm_done
:lhm_already
echo [start.bat] LibreHardwareMonitor already running.
goto lhm_done
:lhm_skip
echo [start.bat] LibreHardwareMonitor not found. Set LHM_PATH_OVERRIDE or install LHM.
echo [start.bat] Continuing without LHM - sensor coverage will be limited.
:lhm_done

echo [start.bat] Launching PC Temperature Monitor...
python main.py
set "RC=%errorlevel%"
popd
exit /b %RC%

:smoke
echo [start.bat] Running smoke test (collectors only, no UI)...
python -m tests.test_collectors
set "RC=%errorlevel%"
popd
exit /b %RC%
