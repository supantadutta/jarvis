"""Add a credential from the UI -> vault (encrypted) + masked metadata."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.deps import set_brain
from app.main import create_app
from app.services.container import Brain


def _brain(tmp_path, vault_key=None) -> Brain:
    s = Settings(
        database_url=f"sqlite:///{tmp_path}/t.db", workspace_root=str(tmp_path / "ws"),
        notes_dir=str(tmp_path / "n"), screenshots_dir=str(tmp_path / "s"),
        audit_dir=str(tmp_path / "a"), chroma_path=str(tmp_path / "c"),
        allow_low_risk_write=True, vault_key=vault_key,
    )
    s.ensure_dirs()
    return Brain(s, use_mock=True)


def test_add_credential_masked_and_listed(tmp_path):
    set_brain(_brain(tmp_path))
    with TestClient(create_app()) as c:
        r = c.post("/api/credentials", json={
            "name": "gmail", "platform": "google", "kind": "password",
            "username": "me@gmail.com", "secret": "hunter2"})
        assert r.status_code == 200 and r.json()["added"] == "gmail"
        creds = c.get("/api/credentials").json()["credentials"]
        cred = next(c2 for c2 in creds if c2["name"] == "gmail")
        assert "@gmail.com" not in cred["username"]  # masked
        assert "hunter2" not in c.get("/api/credentials").text


def test_add_credential_requires_name_platform(tmp_path):
    set_brain(_brain(tmp_path))
    with TestClient(create_app()) as c:
        assert c.post("/api/credentials", json={"name": "x"}).status_code == 400


def test_secret_encrypted_in_vault(tmp_path):
    pytest.importorskip("cryptography")
    from app.security.credentials import FernetVault

    brain = _brain(tmp_path, vault_key=FernetVault.generate_key())
    set_brain(brain)
    with TestClient(create_app()) as c:
        c.post("/api/credentials", json={"name": "splunk", "platform": "splunk",
                                         "secret": "topsecret-token"})
    assert brain.vault.get("cred:splunk") == "topsecret-token"
    with open(f"{brain.settings.chroma_path}/vault.json") as fh:
        assert "topsecret-token" not in fh.read()
