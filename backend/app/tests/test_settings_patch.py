"""Runtime policy updates via PATCH /settings (guard rebuilt; secrets immutable)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.deps import set_brain
from app.main import create_app
from app.security.permissions import Decision, GuardRequest, PermissionLevel as P


@pytest.fixture
def client(brain):
    set_brain(brain)
    with TestClient(create_app()) as c:
        yield c, brain


def test_patch_toggles_low_risk_write_and_rebuilds_guard(client):
    c, brain = client
    # Start: auto-write enabled (conftest) -> LOW_RISK_WRITE auto-allows.
    assert brain.guard.evaluate(GuardRequest("n", P.LOW_RISK_WRITE)).decision == Decision.AUTO_ALLOW
    r = c.patch("/api/settings", json={"allow_low_risk_write": False})
    assert r.status_code == 200 and r.json()["applied"]["allow_low_risk_write"] is False
    # Guard rebuilt: now LOW_RISK_WRITE requires approval.
    assert brain.guard.evaluate(GuardRequest("n", P.LOW_RISK_WRITE)).decision == Decision.REQUIRES_APPROVAL
    # Executor uses the same (rebuilt) guard instance.
    assert brain.executor.guard is brain.guard


def test_patch_updates_cascade_budget(client):
    c, brain = client
    r = c.patch("/api/settings", json={"max_cascade_attempts": 2})
    assert r.status_code == 200
    assert brain.settings.max_cascade_attempts == 2


def test_patch_ignores_secret_keys(client):
    c, brain = client
    r = c.patch("/api/settings", json={"openai_api_key": "sk-evil", "allow_network": False})
    body = r.json()
    assert "openai_api_key" not in body["applied"]
    assert body["applied"]["allow_network"] is False
    assert brain.settings.openai_api_key != "sk-evil"


def test_patch_no_valid_keys_400(client):
    c, _ = client
    assert c.patch("/api/settings", json={"nonsense": 1}).status_code == 400


def test_patch_reflected_in_settings_summary(client):
    c, _ = client
    c.patch("/api/settings", json={"default_mode": "FAST_MODE"})
    assert c.get("/api/settings").json()["default_mode"] == "FAST_MODE"
