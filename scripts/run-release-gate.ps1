$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$pythonExe = Join-Path $repoRoot "venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
  Write-Error "Python venv not found at $pythonExe"
}

& $pythonExe scripts\run_release_gate.py @args
exit $LASTEXITCODE
