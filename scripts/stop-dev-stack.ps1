$ErrorActionPreference = "SilentlyContinue"

Write-Host "Stopping local dev services on ports 3000 and 8001..." -ForegroundColor Cyan

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

    Stop-Process -Id $ProcessId -Force
    Start-Sleep -Milliseconds 120
    $stillRunning = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction SilentlyContinue
    return -not [bool]$stillRunning
}

$ports = @(3000, 8001)
$killed = @()

foreach ($port in $ports) {
    $connections = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    foreach ($conn in $connections) {
        if ($killed -notcontains $conn.OwningProcess) {
            if (Stop-ProcessTree -ProcessId $conn.OwningProcess) {
                $killed += $conn.OwningProcess
                Write-Host "Stopped PID $($conn.OwningProcess) on port $port"
            } else {
                Write-Host "Could not stop PID $($conn.OwningProcess) on port $port" -ForegroundColor Red
            }
        }
    }
}

Write-Host "Stopping API reload watcher processes..." -ForegroundColor Cyan
$apiWatchers = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -match "python(.exe)?$" -and $_.CommandLine -match "uvicorn\s+main:app"
}

foreach ($proc in $apiWatchers) {
    if ($killed -notcontains $proc.ProcessId) {
        if (Stop-ProcessTree -ProcessId $proc.ProcessId) {
            $killed += $proc.ProcessId
            Write-Host "Stopped API watcher PID $($proc.ProcessId)"
        } else {
            Write-Host "Could not stop API watcher PID $($proc.ProcessId)" -ForegroundColor Red
        }
    }
}

Write-Host "Stopping frontend watcher processes..." -ForegroundColor Cyan
$frontendWatchers = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -match "node(.exe)?$" -and $_.CommandLine -match "react-scripts start"
}

foreach ($proc in $frontendWatchers) {
    if ($killed -notcontains $proc.ProcessId) {
        if (Stop-ProcessTree -ProcessId $proc.ProcessId) {
            $killed += $proc.ProcessId
            Write-Host "Stopped frontend watcher PID $($proc.ProcessId)"
        } else {
            Write-Host "Could not stop frontend watcher PID $($proc.ProcessId)" -ForegroundColor Red
        }
    }
}

Write-Host "Stopping Stripe listener processes..." -ForegroundColor Cyan
$stripeProcs = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -match "stripe(.exe)?$" -and $_.CommandLine -match "listen --forward-to http://127.0.0.1:8000/api/payments/webhook"
}

foreach ($proc in $stripeProcs) {
    if (Stop-ProcessTree -ProcessId $proc.ProcessId) {
        Write-Host "Stopped Stripe listener PID $($proc.ProcessId)"
    } else {
        Write-Host "Could not stop Stripe listener PID $($proc.ProcessId)" -ForegroundColor Red
    }
}

Write-Host "Done." -ForegroundColor Green
