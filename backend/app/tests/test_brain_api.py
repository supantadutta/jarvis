"""Cognitive Processing Engine v2 — /api/brain/* endpoints."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.deps import set_brain
from app.main import create_app


@pytest.fixture
def mock_web(monkeypatch):
    from app.tools.builtin import web

    monkeypatch.setattr(web, "do_search", lambda q, **k: [
        {"title": "T", "url": "https://example.com/x", "snippet": ""}])
    monkeypatch.setattr(web, "do_fetch", lambda url, max_chars=20000: "content")


@pytest.fixture
def client(brain):
    set_brain(brain)
    with TestClient(create_app()) as c:
        yield c, brain


def test_brain_analyze(client):
    c, _ = client
    r = c.post("/api/brain/analyze", json={"command": "write a python script"})
    assert r.status_code == 200
    body = r.json()
    assert body["task_type"] == "coding"
    assert "required_skills" in body


def test_brain_plan_returns_dag(client):
    c, _ = client
    r = c.post("/api/brain/plan", json={"command": "research AI and write a verified report"})
    body = r.json()
    assert body["strategy"]
    assert body["plan"]["nodes"]
    assert any(n["id"] == "reason" for n in body["plan"]["nodes"])


def test_brain_execute_inline_and_graph_lookup(client, mock_web):
    c, brain = client
    r = c.post("/api/brain/execute", json={"command": "research AI and reason about it"})
    body = r.json()
    assert body["task_id"]
    assert "nodes" in body
    # The graph run is retrievable.
    g = c.get(f"/api/brain/graph/{body['task_id']}")
    assert g.status_code == 200
    assert g.json()["goal"]


def test_brain_execute_background_enqueues_job(client, mock_web):
    import time

    c, _ = client  # lifespan already started the background worker
    r = c.post("/api/brain/execute", json={"command": "research AI", "background": True})
    body = r.json()
    assert body["background"] is True and body["job_id"]
    # Poll the queue until the background job leaves the queued/running state.
    final = None
    for _ in range(50):
        jobs = c.get("/api/brain/queue").json()["jobs"]
        job = next((j for j in jobs if j["id"] == body["job_id"]), None)
        if job and job["status"] in ("completed", "failed"):
            final = job
            break
        time.sleep(0.05)
    assert final is not None and final["status"] == "completed"
    # The graph result was stored for retrieval.
    assert c.get(f"/api/brain/graph/{body['task_id']}").status_code == 200


def test_brain_status(client):
    c, _ = client
    body = c.get("/api/brain/status").json()
    assert body["resources"]["cpu_count"] >= 1
    assert "response_cache" in body
    assert "memory_layers" in body


def test_brain_memory_search_privacy(client):
    c, brain = client
    brain.layered_memory.remember("semantic", "my bank pin is private", source="user", privacy=5)
    brain.layered_memory.remember("semantic", "python is great", source="user", privacy=1)
    cloud = c.post("/api/brain/memory/search",
                   json={"query": "bank or python", "for_cloud": True}).json()
    assert all(h["privacy"] < 3 for h in cloud["hits"])


def test_brain_evaluate_updates_performance(client):
    c, _ = client
    r = c.post("/api/brain/evaluate", json={
        "task_id": "t1", "model_key": "ollama/llama3.1", "task_type": "coding",
        "verifier_score": 0.9, "completeness": 0.9, "factuality": 0.9})
    assert r.status_code == 200
    assert r.json()["passed"] is True


def test_brain_benchmarks_run(client):
    c, _ = client
    body = c.post("/api/brain/benchmarks/run").json()
    assert body["passed"] is True
    assert body["overall_score"] >= 0.8


def test_brain_models_health_includes_leaderboard(client):
    c, _ = client
    body = c.get("/api/brain/models/health").json()
    assert "health" in body and "leaderboard" in body
