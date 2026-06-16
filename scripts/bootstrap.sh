#!/usr/bin/env bash
# JARVIS bootstrap (Linux/macOS): venv + deps + .env + tests.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> Creating Python venv"
python3 -m venv backend/.venv
# shellcheck disable=SC1091
source backend/.venv/bin/activate

echo "==> Installing backend dependencies"
pip install --upgrade pip >/dev/null
pip install -r backend/requirements.txt

if [ ! -f .env ]; then
  echo "==> Creating .env from .env.example"
  cp .env.example .env
fi

echo "==> Running tests"
(cd backend && python -m pytest -q)

cat <<'EOF'

JARVIS is ready.

  Next steps:
    1. (Optional) Install Ollama and pull a model:  ollama pull llama3.1
    2. Edit .env (Telegram token, cloud keys) if desired.
    3. Start the API:  make run    (or)   cd backend && .venv/bin/uvicorn app.main:app --reload
    4. Open http://localhost:8000/docs

EOF
