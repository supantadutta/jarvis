"""API authentication + CORS lockdown."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import Settings
from app.deps import set_brain
from app.main import create_app
from app.services.container import Brain


def _brain(tmp_path, **overrides) -> Brain:
    s = Settings(
        database_url=f"sqlite:///{tmp_path}/t.db", workspace_root=str(tmp_path / "ws"),
        notes_dir=str(tmp_path / "n"), screenshots_dir=str(tmp_path / "s"),
        audit_dir=str(tmp_path / "a"), chroma_path=str(tmp_path / "c"),
        allow_low_risk_write=True, **overrides,
    )
    s.ensure_dirs()
    return Brain(s, use_mock=True)


def test_auth_disabled_by_default_allows(tmp_path):
    set_brain(_brain(tmp_path))
    with TestClient(create_app()) as c:
        assert c.get("/api/health").status_code == 200
        assert c.post("/api/chat", json={"message": "hi"}).status_code == 200


def test_auth_enabled_blocks_without_token(tmp_path):
    set_brain(_brain(tmp_path, api_token="s3cr3t-token"))
    with TestClient(create_app()) as c:
        # liveness stays public
        assert c.get("/api/health").status_code == 200
        # everything else requires the token
        assert c.post("/api/chat", json={"message": "hi"}).status_code == 401
        assert c.get("/api/models").status_code == 401


def test_auth_enabled_allows_with_bearer(tmp_path):
    set_brain(_brain(tmp_path, api_token="s3cr3t-token"))
    with TestClient(create_app()) as c:
        h = {"Authorization": "Bearer s3cr3t-token"}
        assert c.post("/api/chat", json={"message": "hi"}, headers=h).status_code == 200
        assert c.get("/api/models", headers=h).status_code == 200


def test_auth_enabled_allows_with_api_key_header(tmp_path):
    set_brain(_brain(tmp_path, api_token="s3cr3t-token"))
    with TestClient(create_app()) as c:
        assert c.get("/api/models", headers={"X-API-Key": "s3cr3t-token"}).status_code == 200


def test_auth_wrong_token_rejected(tmp_path):
    set_brain(_brain(tmp_path, api_token="s3cr3t-token"))
    with TestClient(create_app()) as c:
        assert c.get("/api/models", headers={"X-API-Key": "wrong"}).status_code == 401


def test_cors_origins_locked_down(tmp_path):
    b = _brain(tmp_path)
    assert "*" not in b.settings.cors_allow_origins
    assert "http://localhost:3000" in b.settings.cors_allow_origins
