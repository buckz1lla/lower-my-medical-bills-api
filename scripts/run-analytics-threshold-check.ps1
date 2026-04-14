param(
    [string]$ApiBase = "https://api.lowermymedicalbills.com",
    [string]$AnalyticsApiKey = "",
    [double]$MinViewsToPaymentPct = 2.0,
    [double]$MinPaymentToDownloadPct = 70.0,
    [double]$MinAffiliateCtrPct = 1.0,
    [int]$MinViewsForRateCheck = 20,
    [switch]$FailOnLowVolume
)

$ErrorActionPreference = "Stop"

function Get-ApiUri {
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

$funnelUri = Get-ApiUri -Base $ApiBase -Path "api/analytics/funnel-7d" -ApiKey $AnalyticsApiKey
Write-Host "Checking analytics thresholds against $ApiBase" -ForegroundColor Cyan
$funnel = Invoke-RestMethod -Uri $funnelUri -Method GET -TimeoutSec 30

$views = [int]($funnel.counts.results_page_viewed)
$payments = [int]($funnel.counts.payment_completed)
$downloads = [int]($funnel.counts.pdf_downloaded)
$affiliateClicks = [int]($funnel.counts.affiliate_link_clicked)

$viewsToPayment = [double]($funnel.funnel.views_to_payment_percent)
$paymentToDownload = [double]($funnel.funnel.payment_to_download_percent)
$affiliateCtr = [double]($funnel.funnel.affiliate_ctr_percent)

Write-Host "7d counts: views=$views, payments=$payments, downloads=$downloads, affiliateClicks=$affiliateClicks"
Write-Host "7d rates: views->payment=$viewsToPayment%, payment->download=$paymentToDownload%, affiliateCTR=$affiliateCtr%"

$failures = @()

if ($views -lt $MinViewsForRateCheck) {
    $msg = "Low volume window: views=$views (< $MinViewsForRateCheck); skipping rate thresholds."
    if ($FailOnLowVolume) {
        $failures += $msg
    } else {
        Write-Host $msg -ForegroundColor Yellow
    }
} else {
    if ($viewsToPayment -lt $MinViewsToPaymentPct) {
        $failures += "views->payment below threshold: $viewsToPayment < $MinViewsToPaymentPct"
    }
    if ($paymentToDownload -lt $MinPaymentToDownloadPct) {
        $failures += "payment->download below threshold: $paymentToDownload < $MinPaymentToDownloadPct"
    }
    if ($affiliateCtr -lt $MinAffiliateCtrPct) {
        $failures += "affiliate CTR below threshold: $affiliateCtr < $MinAffiliateCtrPct"
    }
}

if ($failures.Count -gt 0) {
    Write-Host "Threshold check FAILED:" -ForegroundColor Red
    foreach ($f in $failures) {
        Write-Host "- $f" -ForegroundColor Red
    }
    exit 1
}

Write-Host "Threshold check passed." -ForegroundColor Green
exit 0
