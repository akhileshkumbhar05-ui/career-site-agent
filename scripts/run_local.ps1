<#
.SYNOPSIS
  Launches the CareerSite Agent backend (FastAPI/uvicorn) and frontend (Vite) together.

.DESCRIPTION
  Opens the backend on http://127.0.0.1:8000 and the frontend on http://127.0.0.1:5173,
  each in its own PowerShell window so you can read logs and stop them with Ctrl+C.
  Port 8000 is the shared backend port (matches the n8n nodes, app config, and the Vite proxy).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\run_local.ps1

.EXAMPLE
  # Backend only (e.g. you don't need the React UI):
  powershell -ExecutionPolicy Bypass -File scripts\run_local.ps1 -NoFrontend
#>

[CmdletBinding()]
param(
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 5173,
    [switch]$NoReload,
    [switch]$NoBackend,
    [switch]$NoFrontend
)

$ErrorActionPreference = "Stop"

# Project root = parent of this script's folder.
$root = Split-Path -Parent $PSScriptRoot
$frontendDir = Join-Path $root "frontend"

function Resolve-VenvPython {
    $candidates = @(
        (Join-Path $root ".venv\Scripts\python.exe"),
        (Join-Path $root "venv\Scripts\python.exe")
    )
    foreach ($p in $candidates) { if (Test-Path $p) { return $p } }
    return $null
}

function Resolve-Node {
    $cmd = Get-Command node -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $candidates = @(
        "$env:ProgramFiles\nodejs\node.exe",
        "$env:LOCALAPPDATA\Programs\nodejs\node.exe",
        "${env:ProgramFiles(x86)}\nodejs\node.exe"
    )
    foreach ($p in $candidates) { if ($p -and (Test-Path $p)) { return $p } }
    return $null
}

# ---------- Backend ----------
if (-not $NoBackend) {
    $python = Resolve-VenvPython
    if (-not $python) {
        Write-Host "[backend] .venv not found. Create it first:" -ForegroundColor Yellow
        Write-Host "          python -m venv .venv" -ForegroundColor Yellow
        Write-Host "          .venv\Scripts\python -m pip install -r requirements.txt" -ForegroundColor Yellow
    } else {
        $uvicornArgs = "-m uvicorn app.main:app --host 127.0.0.1 --port $BackendPort"
        if (-not $NoReload) { $uvicornArgs += " --reload" }
        $backendCmd = "Set-Location '$root'; Write-Host 'Backend -> http://127.0.0.1:$BackendPort  (docs: /docs)' -ForegroundColor Green; & '$python' $uvicornArgs"
        Write-Host "[backend]  starting on http://127.0.0.1:$BackendPort" -ForegroundColor Cyan
        Start-Process powershell -ArgumentList "-NoExit", "-Command", $backendCmd -WorkingDirectory $root
    }
}

# ---------- Frontend ----------
if (-not $NoFrontend) {
    if (-not (Test-Path (Join-Path $frontendDir "node_modules"))) {
        Write-Host "[frontend] node_modules missing. Run 'npm install' in the frontend folder first." -ForegroundColor Yellow
    }

    $npm = Get-Command npm -ErrorAction SilentlyContinue
    if ($npm) {
        $frontendCmd = "Set-Location '$frontendDir'; Write-Host 'Frontend -> http://127.0.0.1:$FrontendPort' -ForegroundColor Green; npm run dev -- --port $FrontendPort"
        Write-Host "[frontend] starting on http://127.0.0.1:$FrontendPort (npm)" -ForegroundColor Cyan
        Start-Process powershell -ArgumentList "-NoExit", "-Command", $frontendCmd -WorkingDirectory $frontendDir
    } else {
        # npm not on PATH: fall back to running the locally installed Vite via node directly.
        $node = Resolve-Node
        $viteJs = Join-Path $frontendDir "node_modules\vite\bin\vite.js"
        if ($node -and (Test-Path $viteJs)) {
            $frontendCmd = "Set-Location '$frontendDir'; Write-Host 'Frontend -> http://127.0.0.1:$FrontendPort' -ForegroundColor Green; & '$node' '$viteJs' --host 127.0.0.1 --port $FrontendPort"
            Write-Host "[frontend] npm not on PATH; starting via node + local vite" -ForegroundColor Cyan
            Start-Process powershell -ArgumentList "-NoExit", "-Command", $frontendCmd -WorkingDirectory $frontendDir
        } else {
            Write-Host "[frontend] Could not find npm or node. Install Node.js, then run 'npm run dev' in the frontend folder." -ForegroundColor Yellow
        }
    }
}

Write-Host ""
Write-Host "Launched. Close each window or press Ctrl+C inside it to stop that server." -ForegroundColor DarkGray
