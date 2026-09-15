@echo off
setlocal EnableExtensions
title LingDong Traffic Platform - services (backend + frontend)
set "ROOT=%~dp0"
set "BE=%ROOT%backend"
set "FE=%ROOT%frontend"

if not exist "%BE%\requirements.txt" (
    echo [ERROR] Run this start.bat from the project source_code directory.
    pause
    exit /b 1
)

rem ---- SUMO -------------------------------------------------
if not exist "%SUMO_HOME%\bin\sumo.exe" (
    if exist "C:\Program Files (x86)\Eclipse\Sumo\bin\sumo.exe" set "SUMO_HOME=C:\Program Files (x86)\Eclipse\Sumo"
)
if not exist "%SUMO_HOME%\bin\sumo.exe" (
    if exist "C:\Program Files\Eclipse\Sumo\bin\sumo.exe" set "SUMO_HOME=C:\Program Files\Eclipse\Sumo"
)
if not exist "%SUMO_HOME%\bin\sumo.exe" (
    where sumo.exe >nul 2>nul
    if errorlevel 1 (
        echo [ERROR] SUMO not found. Set SUMO_HOME to the SUMO installation directory.
        pause
        exit /b 1
    )
)
echo SUMO_HOME=%SUMO_HOME%

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python not found in PATH.
    pause
    exit /b 1
)

rem ---- Python environment -----------------------------------
rem A .venv created on another machine stores THAT machine's absolute paths
rem (pyvenv.cfg "home", Scripts\pip.exe). If this folder was copied/downloaded,
rem the bundled env cannot run here -> verify functionally, then rebuild.
set "VENV=%BE%\.venv"
set "VENV_PY=%VENV%\Scripts\python.exe"
set "VENV_REBUILT="

if exist "%VENV_PY%" (
    "%VENV_PY%" -c "import sys" >nul 2>nul
    if errorlevel 1 (
        echo [1/4] Existing Python env is not usable on this machine ^(bundled from elsewhere^).
        echo       Rebuilding "%VENV%" ...
        rmdir /s /q "%VENV%" 2>nul
        set "VENV_REBUILT=1"
    )
)
if exist "%VENV_PY%" if defined VENV_REBUILT (
    echo [ERROR] Could not remove "%VENV%". Close any program using it, then run again.
    pause
    exit /b 1
)
if not exist "%VENV_PY%" (
    echo [1/4] Creating the backend Python environment...
    python -m venv --system-site-packages "%VENV%"
    if errorlevel 1 (
        echo [ERROR] Could not create the Python environment.
        pause
        exit /b 1
    )
    set "VENV_REBUILT=1"
)
set "PATH=%VENV%\Scripts;%PATH%"
"%VENV_PY%" -c "import sys" >nul 2>nul
if errorlevel 1 (
    echo [ERROR] The Python environment is broken. Delete "%VENV%" and run start.bat again.
    pause
    exit /b 1
)

echo [1/4] Checking backend dependencies...
python -m pip install -r "%BE%\requirements.txt"
if errorlevel 1 (
    echo [ERROR] Backend dependency installation failed.
    pause
    exit /b 1
)
pushd "%BE%"
python -c "import app.main"
if errorlevel 1 (
    popd
    echo [ERROR] Backend import failed. See the error above.
    pause
    exit /b 1
)
popd

where npm >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Node.js/npm not found in PATH.
    pause
    exit /b 1
)
echo [2/4] Checking frontend dependencies...
if not exist "%FE%\node_modules\vite\bin\vite.js" (
    pushd "%FE%"
    call npm install
    if errorlevel 1 (
        popd
        echo [ERROR] Frontend dependency installation failed.
        pause
        exit /b 1
    )
    popd
)
rem Vite's dep cache is keyed to absolute paths: clear it after the folder moved
rem (first run on this machine) so the dev server re-optimizes instead of failing.
if defined VENV_REBUILT if exist "%FE%\node_modules\.vite" (
    echo       Clearing stale frontend build cache...
    rmdir /s /q "%FE%\node_modules\.vite" 2>nul
)

rem Backend + frontend run in THIS window, supervised by run_services.ps1
rem (not cmd "start /b": it can silently fail to spawn children when stdout is
rem  redirected or the console is non-interactive)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_services.ps1" -Backend "%BE%" -Frontend "%FE%"
if errorlevel 1 (
    echo.
    echo [ERROR] Could not start the services. See the messages above.
    echo         Manual fallback ^(two windows^):
    echo           cd /d "%BE%" ^&^& python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
    echo           cd /d "%FE%" ^&^& npm run dev
    pause
    exit /b 1
)

echo.
echo All services have stopped. Press any key to close this window.
pause >nul

