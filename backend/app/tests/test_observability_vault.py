"""Metrics endpoint + structured logging + model-keys-in-vault."""
from __future__ import annotations

import json
import logging

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.deps import set_brain
from app.main import create_app
from app.observability.logging import JsonFormatter
from app.observability.metrics import Metrics
from app.services.container import Brain


# --- metrics ---
def test_metrics_registry_renders_prometheus():
    m = Metrics()
    m.inc("jarvis_http_requests_total", path="/api/chat", method="POST", status=200)
    m.inc("jarvis_http_requests_total", path="/api/chat", method="POST", status=200)
    text = m.render({"jarvis_models_enabled": 4})
    assert 'jarvis_http_requests_total{method="POST",path="/api/chat",status="200"} 2.0' in text
    assert "jarvis_models_enabled 4" in text


def test_metrics_endpoint(brain):
    set_brain(brain)
    with TestClient(create_app()) as c:
        c.post("/api/chat", json={"message": "hi"})
        r = c.get("/api/metrics")
        assert r.status_code == 200
        body = r.text
        assert "jarvis_models_enabled" in body
        assert "jarvis_http_requests_total" in body  # counted by middleware
        assert "jarvis_response_cache_hit_rate" in body


# --- structured logging ---
def test_json_formatter_redacts_secrets():
    rec = logging.LogRecord("x", logging.INFO, __file__, 1,
                            "connecting with api_key=sk-supersecret123456", None, None)
    out = JsonFormatter().format(rec)
    parsed = json.loads(out)
    assert parsed["level"] == "INFO"
    assert "sk-supersecret123456" not in out
    assert "[REDACTED]" in parsed["msg"]


# --- model API keys in the vault ---
def _vault_brain(tmp_path, key: str | None) -> Brain:
    s = Settings(
        database_url=f"sqlite:///{tmp_path}/t.db", workspace_root=str(tmp_path / "ws"),
        notes_dir=str(tmp_path / "n"), screenshots_dir=str(tmp_path / "s"),
        audit_dir=str(tmp_path / "a"), chroma_path=str(tmp_path / "c"),
        allow_low_risk_write=True, vault_key=key,
    )
    s.ensure_dirs()
    return Brain(s, use_mock=True)


def test_added_model_key_registered_as_masked_credential(tmp_path):
    brain = _vault_brain(tmp_path, key=None)  # NullVault: metadata only
    brain.add_model_source(provider="deepseek", model_name="deepseek-chat",
                           api_key="sk-deepseek-secret-123")
    creds = brain.credentials.list_public()
    cred = next(c for c in creds if c["name"] == "model:deepseek")
    assert cred["kind"] == "token"
    assert "vault_ref" not in cred  # pointer never exposed


def test_added_model_key_encrypted_at_rest_with_vault(tmp_path):
    pytest.importorskip("cryptography")
    from app.security.credentials import FernetVault

    key = FernetVault.generate_key()
    brain = _vault_brain(tmp_path, key=key)
    brain.add_model_source(provider="openai", model_name="gpt-4o",
                           api_key="sk-openai-secret-xyz")
    # Retrievable via the vault, and NOT stored in plaintext on disk.
    assert brain.vault.get("model:openai") == "sk-openai-secret-xyz"
    vault_file = f"{brain.settings.chroma_path}/vault.json"
    with open(vault_file) as fh:
        assert "sk-openai-secret-xyz" not in fh.read()
