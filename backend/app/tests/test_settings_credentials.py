"""Settings summary (no secrets) + masked credentials API."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.deps import set_brain
from app.main import create_app
from app.security.credentials import CredentialMeta
from app.services.container import Brain


@pytest.fixture
def client(tmp_path):
    s = Settings(
        database_url=f"sqlite:///{tmp_path}/t.db", workspace_root=str(tmp_path / "ws"),
        notes_dir=str(tmp_path / "n"), screenshots_dir=str(tmp_path / "s"),
        audit_dir=str(tmp_path / "a"), chroma_path=str(tmp_path / "c"),
        openai_api_key="sk-secret-should-not-leak", allow_low_risk_write=True,
    )
    s.ensure_dirs()
    brain = Brain(s, use_mock=True)
    brain.credentials.register(CredentialMeta(
        name="splunk", platform="splunk", kind="token",
        username="analyst@corp", vault_ref="ref-1", scopes=["read"],
    ))
    set_brain(brain)
    with TestClient(create_app()) as c:
        yield c, brain


def test_settings_summary_no_secrets(client):
    c, _ = client
    r = c.get("/api/settings")
    assert r.status_code == 200
    body = r.json()
    assert body["providers_configured"]["openai"] is True
    assert body["providers_configured"]["anthropic"] is False
    # The actual secret must never appear anywhere in the response.
    assert "sk-secret-should-not-leak" not in r.text


def test_credentials_listed_masked(client):
    c, _ = client
    r = c.get("/api/credentials")
    creds = r.json()["credentials"]
    assert creds and creds[0]["name"] == "splunk"
    assert "@corp" not in creds[0]["username"]  # masked
    assert "vault_ref" not in creds[0]


def test_credential_revoke(client):
    c, _ = client
    r = c.post("/api/credentials/splunk/revoke")
    assert r.status_code == 200 and r.json()["revoked"] is True
    assert c.get("/api/credentials").json()["credentials"][0]["revoked"] is True


def test_revoke_unknown_404(client):
    c, _ = client
    assert c.post("/api/credentials/nope/revoke").status_code == 404
