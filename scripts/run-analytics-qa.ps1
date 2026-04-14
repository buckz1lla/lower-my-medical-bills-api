param(
    [string]$ApiBase = "http://127.0.0.1:8000",
    [string]$AnalyticsApiKey = "",
    [switch]$SmokeTrack,
    [switch]$AllowFallback
)

$ErrorActionPreference = "Stop"

function Build-Uri {
    param(
        [string]$Base,
        [string]$Path,
        [string]$ApiKey
    )

    $u = "$($Base.TrimEnd('/'))/$($Path.TrimStart('/'))"
    if ([string]::IsNullOrWhiteSpace($ApiKey)) {
        return $u
    }
    return "$u?api_key=$ApiKey"
}

function Invoke-Check {
    param(
        [string]$Name,
        [string]$Uri
    )

    try {
        $resp = Invoke-RestMethod -Uri $Uri -Method GET -TimeoutSec 30
        [PSCustomObject]@{
            check = $Name
            status = "PASS"
            detail = "GET succeeded"
            payload = $resp
        }
    }
    catch {
        [PSCustomObject]@{
            check = $Name
            status = "FAIL"
            detail = $_.Exception.Message
            payload = $null
        }
    }
}

Write-Host "Analytics QA starting against $ApiBase" -ForegroundColor Cyan

$checks = @()
$healthUri = Build-Uri -Base $ApiBase -Path "health" -ApiKey ""
$funnelUri = Build-Uri -Base $ApiBase -Path "api/analytics/funnel" -ApiKey $AnalyticsApiKey
$funnel7dUri = Build-Uri -Base $ApiBase -Path "api/analytics/funnel-7d" -ApiKey $AnalyticsApiKey
$revenueUri = Build-Uri -Base $ApiBase -Path "api/analytics/revenue" -ApiKey $AnalyticsApiKey

$checks += Invoke-Check -Name "API health" -Uri $healthUri
$checks += Invoke-Check -Name "Analytics funnel (today)" -Uri $funnelUri
$checks += Invoke-Check -Name "Analytics funnel (7d)" -Uri $funnel7dUri
$checks += Invoke-Check -Name "Analytics revenue" -Uri $revenueUri

if ($SmokeTrack) {
    $trackUri = "$($ApiBase.TrimEnd('/'))/api/analytics/track"
    $analysisId = "qa-smoke-" + [guid]::NewGuid().ToString("N")
    $bodyObj = @{
        event = "results_page_viewed"
        data = @{
            analysisId = $analysisId
            source = "qa-script"
        }
        timestamp = (Get-Date).ToString("o")
        userAgent = "run-analytics-qa.ps1"
    }

    try {
        $trackResp = Invoke-RestMethod -Uri $trackUri -Method POST -ContentType "application/json" -Body ($bodyObj | ConvertTo-Json -Depth 6) -TimeoutSec 30
        $storage = "$($trackResp.storage)"
        $isFallback = ($storage -ne "supabase")
        $status = if ($isFallback -and -not $AllowFallback) { "FAIL" } else { "PASS" }
        $detail = "storage=$storage; analysisId=$analysisId"
        if ($isFallback -and -not $AllowFallback) {
            $detail = "$detail; expected=supabase"
        }
        $checks += [PSCustomObject]@{
            check = "Smoke track write"
            status = $status
            detail = $detail
            payload = $trackResp
        }
    }
    catch {
        $checks += [PSCustomObject]@{
            check = "Smoke track write"
            status = "FAIL"
            detail = $_.Exception.Message
            payload = $null
        }
    }
}

$checks | Select-Object check, status, detail | Format-Table -AutoSize

$failed = @($checks | Where-Object { $_.status -eq "FAIL" })
if ($failed.Count -gt 0) {
    Write-Host "Analytics QA finished with failures." -ForegroundColor Red
    exit 1
}

Write-Host "Analytics QA passed." -ForegroundColor Green
exit 0