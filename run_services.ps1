# ============================================================
#  Single-window supervisor: run backend + frontend in ONE console.
#  Called by start.bat:
#    powershell -NoProfile -ExecutionPolicy Bypass -File run_services.ps1 -Backend <dir> -Frontend <dir>
#
#  Why not cmd "start /b": in a non-interactive console (or when stdout is
#  redirected) it can silently fail to spawn the child - symptom: the backend
#  never becomes ready and nothing is printed. Start-Process -NoNewWindow
#  attaches both services to THIS console, so logs appear in one window and
#  closing the window (or Ctrl+C) stops everything.
#
#  NOTE: keep this file ASCII-only. Windows PowerShell 5.1 decodes a .ps1
#  without BOM as ANSI; non-ASCII comments can break parsing.
# ============================================================
param(
    [Parameter(Mandatory = $true)][string]$Backend,
    [Parameter(Mandatory = $true)][string]$Frontend,
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 5173,
    [switch]$NoBrowser,
    [int]$ReadyTimeoutSec = 60,
    [int]$FrontendTimeoutSec = 90
)

$ErrorActionPreference = 'Stop'

function Say($msg) { Write-Host $msg }

# Stop stale listeners first (a previous run that was not closed cleanly).
foreach ($port in @($BackendPort, $FrontendPort)) {
    $conn = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($conn) {
        Say "       Port $port is busy (PID $($conn.OwningProcess)) - stopping the stale process..."
        Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue
        Start-Sleep -Milliseconds 600
    }
}

Say "[3/4] Starting backend on port $BackendPort ..."
$be = Start-Process -FilePath 'python' `
    -ArgumentList '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1',
                  '--port', "$BackendPort", '--log-level', 'warning' `
    -WorkingDirectory $Backend -NoNewWindow -PassThru

$ready = $false
for ($i = 0; $i -lt $ReadyTimeoutSec; $i++) {
    $alive = $true
    try { $alive = -not $be.HasExited } catch { $alive = $false }
    if (-not $alive) { break }
    try {
        $r = Invoke-RestMethod -Uri "http://127.0.0.1:$BackendPort/api/v1/simulate/status" -TimeoutSec 2
        if ($r.code -eq 0) { $ready = $true; break }
    } catch { }
    Start-Sleep -Seconds 1
}

if (-not $ready) {
    $alive = $true
    try { $alive = -not $be.HasExited } catch { $alive = $false }
    if (-not $alive) {
        Say "[ERROR] Backend exited early - see the messages above."
    } else {
        Say "[ERROR] Backend did not become ready within $ReadyTimeoutSec s."
        Stop-Process -Id $be.Id -Force -ErrorAction SilentlyContinue
    }
    exit 1
}

Say ""
Say "============================================================"
Say "  Services are running in THIS single window:"
Say "    backend  : http://127.0.0.1:$BackendPort   (quiet logs)"
Say "    frontend : http://localhost:$FrontendPort"
Say "  Close this window (or press Ctrl+C) to stop ALL services."
Say "============================================================"
Say ""

Say "[4/4] Starting frontend on port $FrontendPort (logs below)..."
# npm is npm.cmd on Windows (a batch file) which CreateProcess cannot run
# directly, so launch it explicitly through cmd.exe.
$fe = Start-Process -FilePath 'cmd.exe' -ArgumentList '/c', 'npm run dev' `
    -WorkingDirectory $Frontend -NoNewWindow -PassThru

# IMPORTANT: wait until the dev server actually answers BEFORE opening the
# browser - otherwise the tab opens too early and shows "can't reach this page"
# (the first Vite request also pre-bundles dependencies, so it can take a while).
$feReady = $false
for ($i = 0; $i -lt $FrontendTimeoutSec; $i++) {
    $feAlive = $true
    try { $feAlive = -not $fe.HasExited } catch { $feAlive = $false }
    if (-not $feAlive) { break }
    try {
        $resp = Invoke-WebRequest -Uri "http://127.0.0.1:$FrontendPort" -TimeoutSec 2 -UseBasicParsing
        if ($resp.StatusCode -eq 200) { $feReady = $true; break }
    } catch { }
    Start-Sleep -Seconds 1
}

if ($feReady) {
    Say "  Frontend is ready: http://localhost:$FrontendPort"
    Say "  Opening the browser now..."
    if (-not $NoBrowser) { Start-Process "http://localhost:$FrontendPort" | Out-Null }
} else {
    $feAlive = $true
    try { $feAlive = -not $fe.HasExited } catch { $feAlive = $false }
    if (-not $feAlive) {
        Say "[ERROR] Frontend exited early - see the npm output above."
    } else {
        Say "[ERROR] Frontend did not answer on port $FrontendPort within $FrontendTimeoutSec s."
        Say "        The dev server may still be starting; open http://localhost:$FrontendPort manually."
    }
}

# Keep the window alive; closing it / Ctrl+C takes both services down.
Wait-Process -Id $be.Id, $fe.Id -ErrorAction SilentlyContinue
Say "All services stopped."
