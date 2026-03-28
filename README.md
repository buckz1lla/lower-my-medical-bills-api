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
