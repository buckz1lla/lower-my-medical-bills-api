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

$funnelUri = Build-Uri -Base $ApiBase -Path "api/analytics/funnel-7d" -ApiKey $AnalyticsApiKey
$revenueUri = Build-Uri -Base $ApiBase -Path "api/analytics/revenue?days=7" -ApiKey $AnalyticsApiKey

Write-Host "Fetching weekly funnel metrics from $ApiBase" -ForegroundColor Cyan
$funnel = Invoke-RestMethod -Uri $funnelUri -Method GET -TimeoutSec 30
$revenue = Invoke-RestMethod -Uri $revenueUri -Method GET -TimeoutSec 30

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
