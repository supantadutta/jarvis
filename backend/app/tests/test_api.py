"""API smoke tests using FastAPI TestClient with a mock-backed Brain."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.deps import set_brain
from app.main import create_app


@pytest.fixture
def client(brain):
    set_brain(brain)  # inject mock-backed brain
    app = create_app()
    with TestClient(app) as c:
        yield c


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["models_enabled"] > 0


def test_chat(client):
    r = client.post("/api/chat", json={"message": "hello jarvis"})
    assert r.status_code == 200
    body = r.json()
    assert body["answer"]
    assert body["task_id"]


def test_chat_with_mode(client):
    r = client.post("/api/chat", json={"message": "plan my day", "mode": "DEEP_WORK_MODE"})
    assert r.status_code == 200
    assert r.json()["mode"] == "DEEP_WORK_MODE"


def test_chat_invalid_mode(client):
    r = client.post("/api/chat", json={"message": "x", "mode": "NOPE"})
    assert r.status_code == 400


def test_list_models(client):
    r = client.get("/api/models")
    assert r.status_code == 200
    assert len(r.json()["models"]) >= 4


def test_list_tools(client):
    r = client.get("/api/tools")
    assert len(r.json()["tools"]) >= 25


def test_list_agents(client):
    r = client.get("/api/agents")
    keys = {a["key"] for a in r.json()["agents"]}
    assert {"supervisor", "planner", "verifier", "soc"} <= keys


def test_memory_add_and_search(client):
    client.post("/api/memory/add", json={"text": "the wifi password note is in the vault"})
    r = client.post("/api/memory/search", json={"query": "wifi password", "limit": 3})
    assert r.json()["hits"]


def test_emergency_stop_toggle(client):
    r = client.post("/api/control/stop", json={"engaged": True})
    assert r.json()["emergency_stop"] is True
    client.post("/api/control/stop", json={"engaged": False})


def test_approvals_empty(client):
    r = client.get("/api/approvals/pending")
    assert r.status_code == 200


def test_workflows_listed(client):
    r = client.get("/api/workflows")
    keys = {w["key"] for w in r.json()["workflows"]}
    assert "morning_briefing" in keys
