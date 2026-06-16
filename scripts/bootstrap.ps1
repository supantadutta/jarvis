# JARVIS bootstrap (Windows PowerShell): venv + deps + .env + tests.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

Write-Host "==> Creating Python venv"
python -m venv backend\.venv
$py = "backend\.venv\Scripts\python.exe"

Write-Host "==> Installing backend dependencies"
& $py -m pip install --upgrade pip | Out-Null
& $py -m pip install -r backend\requirements.txt

if (-not (Test-Path ".env")) {
  Write-Host "==> Creating .env from .env.example"
  Copy-Item .env.example .env
}

Write-Host "==> Running tests"
Push-Location backend
& .venv\Scripts\python.exe -m pytest -q
Pop-Location

Write-Host ""
Write-Host "JARVIS is ready."
Write-Host "  1. (Optional) Install Ollama and run:  ollama pull llama3.1"
Write-Host "  2. Edit .env if desired."
Write-Host "  3. Start the API:  cd backend; .venv\Scripts\uvicorn app.main:app --reload"
Write-Host "  4. Open http://localhost:8000/docs"
