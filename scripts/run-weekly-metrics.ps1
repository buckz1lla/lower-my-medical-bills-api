param(
    [string]$ApiBase = "https://api.lowermymedicalbills.com",
    [string]$AnalyticsApiKey = "",
    [string]$OutputFile = "docs/analytics_weekly_log.md"
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

# Wake up the server before hitting analytics endpoints.
# Free-tier hosts (Render, Railway) can cold-start in 30-90s; without this the
# analytics call itself times out and the whole workflow fails.
function Invoke-Warmup {
    param([string]$Base, [int]$MaxAttempts = 6, [int]$AttemptTimeoutSec = 20)
    $healthUri = "$($Base.TrimEnd('/'))/health"
    for ($i = 1; $i -le $MaxAttempts; $i++) {
        try {
            $resp = Invoke-RestMethod -Uri $healthUri -Method GET -TimeoutSec $AttemptTimeoutSec
            Write-Host "Server ready (attempt $i): status=$($resp.status)" -ForegroundColor Green
            return $true
        } catch {
            Write-Warning "Warmup attempt $i/$MaxAttempts failed: $($_.Exception.Message)"
            if ($i -lt $MaxAttempts) {
                Write-Host "Waiting 15s before retry..." -ForegroundColor Yellow
                Start-Sleep -Seconds 15
            }
        }
    }
    return $false
}

Write-Host "Fetching weekly funnel metrics from $ApiBase" -ForegroundColor Cyan

$serverReady = Invoke-Warmup -Base $ApiBase
if (-not $serverReady) {
    Write-Warning "Server did not respond after warmup. Logging zero-row entry and exiting."
    # Log a zero entry so the PR still opens with a clear record of the outage.
    $today = (Get-Date).ToString("yyyy-MM-dd")
    $entry = @"

## Week Ending: $today

> NOTE: API unreachable during scheduled run. All values are 0.

- Views: 0
- Checkout Started: 0
- Payments: 0
- Downloads: 0
- Affiliate Clicks: 0

- Views->Payment %: 0.0
- Payment->Download %: 0.0
- Views->Download %: 0.0
- Affiliate CTR %: 0.0

- Total Revenue (7d): 0
- Average Order Value (7d): 0.0
- Payment Count (7d): 0

"@
    if (-not (Test-Path $OutputFile)) {
        New-Item -Path $OutputFile -ItemType File -Force | Out-Null
        Add-Content -Path $OutputFile -Value "# Weekly Metrics Log`n"
    }
    Add-Content -Path $OutputFile -Value $entry
    Write-Host "Zero-row entry appended to $OutputFile" -ForegroundColor Yellow
    exit 0
}

$funnelUri = Build-Uri -Base $ApiBase -Path "api/analytics/funnel-7d" -ApiKey $AnalyticsApiKey
$revenueUri = Build-Uri -Base $ApiBase -Path "api/analytics/revenue?days=7" -ApiKey $AnalyticsApiKey

$funnel = Invoke-RestMethod -Uri $funnelUri -Method GET -TimeoutSec 60
$revenue = Invoke-RestMethod -Uri $revenueUri -Method GET -TimeoutSec 60

$today = (Get-Date).ToString("yyyy-MM-dd")
$counts = $funnel.counts
$rates = $funnel.funnel

$entry = @"

## Week Ending: $today

- Views: $($counts.results_page_viewed)
- Checkout Started: $($counts.checkout_started)
- Payments: $($counts.payment_completed)
- Downloads: $($counts.pdf_downloaded)
- Affiliate Clicks: $($counts.affiliate_link_clicked)

- Views->Payment %: $($rates.views_to_payment_percent)
- Payment->Download %: $($rates.payment_to_download_percent)
- Views->Download %: $($rates.views_to_download_percent)
- Affiliate CTR %: $($rates.affiliate_ctr_percent)

- Total Revenue (7d): $($revenue.total_revenue)
- Average Order Value (7d): $($revenue.average_order_value)
- Payment Count (7d): $($revenue.payment_count)

"@

if (-not (Test-Path $OutputFile)) {
    New-Item -Path $OutputFile -ItemType File -Force | Out-Null
    Add-Content -Path $OutputFile -Value "# Weekly Metrics Log`n"
}

Add-Content -Path $OutputFile -Value $entry
Write-Host "Weekly metrics appended to $OutputFile" -ForegroundColor Green
