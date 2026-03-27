param(
    [switch]$NoStripe
)

$ErrorActionPreference = "Stop"

$apiRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$frontendRoot = (Resolve-Path (Join-Path $apiRoot "..\lower-my-medical-bills-frontend")).Path

function Stop-ProcessTree {
    param([int]$ProcessId)

    if (-not $ProcessId) {
        return $false
    }

    taskkill.exe /PID $ProcessId /T /F | Out-Null
    Start-Sleep -Milliseconds 120

    $stillRunning = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction SilentlyContinue
    if (-not $stillRunning) {
        return $true
    }

    Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 120
    $stillRunning = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction SilentlyContinue
    return -not [bool]$stillRunning
}

function Stop-StaleListeners {
    param([int[]]$Ports)

    $killed = @()
    foreach ($port in $Ports) {
        $connections = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
        foreach ($conn in $connections) {
            if ($killed -notcontains $conn.OwningProcess) {
                if (Stop-ProcessTree -ProcessId $conn.OwningProcess) {
                    $killed += $conn.OwningProcess
                    Write-Host "Stopped stale PID $($conn.OwningProcess) on port $port" -ForegroundColor Yellow
                } else {
                    Write-Host "Could not stop PID $($conn.OwningProcess) on port $port" -ForegroundColor Red
                }
            }
        }
    }
}

if (-not (Test-Path $frontendRoot)) {
    throw "Frontend folder not found: $frontendRoot"
}

$venvPython = Join-Path $apiRoot "venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    throw "API virtual environment not found: $venvPython"
}

function Start-ServiceWindow {
    param(
        [Parameter(Mandatory = $true)][string]$Title,
        [Parameter(Mandatory = $true)][string]$WorkingDirectory,
        [Parameter(Mandatory = $true)][string]$Command
    )

    $wrappedCommand = "$Host.UI.RawUI.WindowTitle = '$Title'; Set-Location '$WorkingDirectory'; $Command"

    Start-Process powershell.exe -WorkingDirectory $WorkingDirectory -ArgumentList @(
        "-NoExit",
        "-ExecutionPolicy", "Bypass",
        "-Command", $wrappedCommand
    ) | Out-Null
}

Write-Host "Starting API, Frontend, and optional Stripe listener..." -ForegroundColor Cyan

$stopScript = Join-Path $PSScriptRoot "stop-dev-stack.ps1"
if (Test-Path $stopScript) {
    & $stopScript
}

# Ensure stale processes do not keep old settings bound to dev ports.
Stop-StaleListeners -Ports @(3000, 8001)
Start-Sleep -Milliseconds 400

Start-ServiceWindow -Title "LMMB API" -WorkingDirectory $apiRoot -Command "& '$venvPython' -m uvicorn main:app --app-dir '$apiRoot' --host 127.0.0.1 --port 8001"
Start-Sleep -Milliseconds 300

Start-ServiceWindow -Title "LMMB Frontend" -WorkingDirectory $frontendRoot -Command "npm start"
Start-Sleep -Milliseconds 300

if (-not $NoStripe) {
    Start-ServiceWindow -Title "LMMB Stripe Listener" -WorkingDirectory $apiRoot -Command "stripe listen --forward-to http://127.0.0.1:8001/api/payments/webhook"
} else {
    Write-Host "Skipped Stripe listener because -NoStripe was provided." -ForegroundColor Yellow
}

Write-Host "Done. Open http://localhost:3000 and login at /owner/login if needed." -ForegroundColor Green
