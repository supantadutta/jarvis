"""API authentication.

A personal automation platform that can control your PC, files, and accounts must
not be open to anyone who can reach the port. Auth is enforced when
`api_auth_enabled` is true OR an `api_token` is configured. When no token is set
(pure local dev), auth is disabled but the app logs a loud warning at startup.

Accepts either `Authorization: Bearer <token>` or `X-API-Key: <token>`. Uses a
constant-time comparison. Liveness (`/api/health`) stays public for probes.
"""
from __future__ import annotations

import hmac
import logging

from fastapi import Request
from fastapi.responses import JSONResponse

from app.deps import get_brain

logger = logging.getLogger("jarvis.auth")

PUBLIC_PATHS = {"/api/health"}


def _present_token(request: Request) -> str | None:
    auth = request.headers.get("authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.headers.get("x-api-key")


def check_http_auth(request: Request) -> JSONResponse | None:
    """Return a 401 response if auth is required and the token is missing/invalid,
    else None. Used by the HTTP auth middleware (websockets bypass this)."""
    path = request.url.path
    if not path.startswith("/api") or path in PUBLIC_PATHS:
        return None
    settings = get_brain().settings
    if not settings.auth_required:
        return None  # local dev: disabled (warned at startup)
    token = settings.api_token or ""
    presented = _present_token(request) or ""
    if not token or not hmac.compare_digest(presented, token):
        return JSONResponse(
            {"detail": "Missing or invalid API token."}, status_code=401,
            headers={"WWW-Authenticate": "Bearer"},
        )
    return None
