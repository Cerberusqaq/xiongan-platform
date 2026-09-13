@echo off
setlocal EnableExtensions
set "ROOT=%~dp0"
set "BE=%ROOT%backend"
set "FE=%ROOT%frontend"

if not exist "%BE%\requirements.txt" (
    echo [ERROR] Run this start.bat from the project source_code directory.
    pause
    exit /b 1
)

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

if not exist "%BE%\.venv\Scripts\python.exe" (
    echo [1/4] Creating the backend Python environment...
    python -m venv --system-site-packages "%BE%\.venv"
    if errorlevel 1 (
        echo [ERROR] Could not create the Python environment.
        pause
        exit /b 1
    )
)
set "PATH=%BE%\.venv\Scripts;%PATH%"
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

echo [3/4] Starting backend on port 8000...
start "traffic-backend" /D "%BE%" cmd /k "python -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
powershell -NoProfile -Command "$ok=$false; for($i=0;$i -lt 30;$i++){try{$r=Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/v1/simulate/status' -TimeoutSec 2; if($r.code -eq 0){$ok=$true;break}}catch{}; Start-Sleep -Seconds 1}; if(-not $ok){exit 1}"
if errorlevel 1 (
    echo [ERROR] Backend did not become ready. Check the traffic-backend window.
    pause
    exit /b 1
)

echo [4/4] Starting frontend on port 5173...
start "traffic-frontend" /D "%FE%" cmd /k "npm run dev"
timeout /t 4 /nobreak >nul
start "" "http://localhost:5173"
echo Ready. Keep both service windows open during the demo.
pause
