#!/usr/bin/env bash
# Quick health probe for the JARVIS backend (and optional Ollama).
set -uo pipefail
API="${1:-http://localhost:8000}"

echo "==> Backend health ($API/api/health)"
if curl -fsS "$API/api/health" >/tmp/jarvis_health.json 2>/dev/null; then
  python3 -m json.tool </tmp/jarvis_health.json
else
  echo "  Backend not reachable."
  exit 1
fi

echo "==> Ollama (${OLLAMA_BASE_URL:-http://localhost:11434}/api/tags)"
if curl -fsS "${OLLAMA_BASE_URL:-http://localhost:11434}/api/tags" >/dev/null 2>&1; then
  echo "  Ollama is up."
else
  echo "  Ollama not reachable (local models unavailable; mock/cloud still work)."
fi
