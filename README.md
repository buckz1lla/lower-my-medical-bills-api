# lower-my-medical-bills-api
FastAPI Backend for my project

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
