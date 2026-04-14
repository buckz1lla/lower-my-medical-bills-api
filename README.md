# lower-my-medical-bills-api
FastAPI Backend for my project

## Production configuration

Create a `.env` file based on [.env.example](.env.example) and set at minimum:

- `CORS_ORIGINS=https://lowermymedicalbills.com,https://www.lowermymedicalbills.com`
- `FRONTEND_URL=https://lowermymedicalbills.com`
- `COOKIE_SECURE=true`
- `STRIPE_SECRET_KEY=...`
- `STRIPE_WEBHOOK_SECRET=...`
- `STRIPE_PRICE_ID=...`
- `ADMIN_DASHBOARD_PASSWORD=...`
- `ADMIN_SESSION_SECRET=...`

Use a production `DATABASE_URL` for persistence.

## Deployment smoke checks

After deployment and DNS setup:

1. Open `/health` on API and verify status is healthy.
2. Confirm frontend can call API from browser without CORS errors.
3. Run one test checkout and verify webhook delivery.
4. Trigger reminder endpoint and verify links use `FRONTEND_URL`.

## One-click local startup (Windows)

This repo includes scripts to launch the full local stack:

- API (uvicorn on port 8000)
- Frontend (`../lower-my-medical-bills-frontend`, port 3000)
- Stripe webhook listener

### Option 1: Double-click scripts

From this folder:

- `start-dev-stack.cmd`
- `stop-dev-stack.cmd`

### Option 2: PowerShell

```powershell
./scripts/start-dev-stack.ps1
./scripts/stop-dev-stack.ps1
```

To start without Stripe listener:

```powershell
./scripts/start-dev-stack.ps1 -NoStripe
```

### Option 3: VS Code Task button

Use `Terminal -> Run Task` and choose one of:

- `LMMB: Start Full Dev Stack`
- `LMMB: Start Stack (No Stripe)`
- `LMMB: Stop Full Dev Stack`

## Benchmark release gate

Run benchmarks and enforce release thresholds before shipping parser/rule changes.

Default thresholds:

- raw score >= 95%
- weighted score >= 97%
- 0 failing benchmark cases

PowerShell helper:

```powershell
scripts\run-release-gate.ps1
```

Python direct:

```powershell
venv\Scripts\python scripts\run_release_gate.py
```

Override thresholds:

```powershell
venv\Scripts\python scripts\run_release_gate.py --raw-threshold 96 --weighted-threshold 98 --allow-case-failures 0
```

## Analytics operations

This repo now includes a reusable analytics query pack and a weekly runbook:

- `docs/analytics_funnel_queries.sql`
- `docs/analytics_weekly_metrics_checklist.md`

For quick API-level health checks of funnel metrics, run:

```powershell
./scripts/run-analytics-qa.ps1 -ApiBase https://api.lowermymedicalbills.com
```

Optional smoke tracking call and protected endpoint key:

```powershell
./scripts/run-analytics-qa.ps1 -ApiBase https://api.lowermymedicalbills.com -AnalyticsApiKey <your_key> -SmokeTrack
```

By default, `-SmokeTrack` now fails QA if tracking falls back to file storage.
Use `-AllowFallback` only for intentional local fallback testing.

Generate and append a weekly metrics snapshot:

```powershell
./scripts/run-weekly-metrics.ps1 -ApiBase https://api.lowermymedicalbills.com
```

Run threshold checks (with low-volume safeguards):

```powershell
./scripts/run-analytics-threshold-check.ps1 -ApiBase https://api.lowermymedicalbills.com
```

Output log file:

- `docs/analytics_weekly_log.md`

Inspect fallback alert events:

```text
GET /api/analytics/storage-alerts?days=7
```

Automated weekly operations workflow:

- `.github/workflows/analytics-weekly-ops.yml`

Run it on demand (manual dispatch):

1. GitHub UI: Actions -> "Analytics Weekly Ops" -> "Run workflow".
2. GitHub CLI:

```bash
gh workflow run "Analytics Weekly Ops" --repo buckz1lla/lower-my-medical-bills-api
```

Set these optional GitHub settings:

- Repository variable: `ANALYTICS_API_BASE` (defaults to `https://api.lowermymedicalbills.com`)
- Repository secret: `ANALYTICS_API_KEY` (if your analytics endpoints require it)
