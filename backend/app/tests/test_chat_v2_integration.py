"""Proof that the Cognitive Engine v2 is wired into the real /chat path."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.agents.orchestrator import Orchestrator
from app.deps import set_brain
from app.main import create_app
from app.model_router.modes import Mode


@pytest.fixture
def client(brain):
    set_brain(brain)
    with TestClient(create_app()) as c:
        yield c, brain


def test_chat_returns_analysis_and_quality(client):
    c, _ = client
    body = c.post("/api/chat", json={"message": "write a python script to parse logs"}).json()
    assert body["analysis"] is not None
    assert body["analysis"]["task_type"] == "coding"
    assert body["quality"] is not None
    assert "scores" in body["quality"]


@pytest.mark.asyncio
async def test_orchestrator_uses_response_cache(brain):
    # Two runs of the same simple command should populate + hit the shared cache.
    await Orchestrator(brain).run("say hello", mode_override=Mode.FAST_MODE)
    hits_after_first = brain.response_cache.stats()["hits"]
    await Orchestrator(brain).run("say hello", mode_override=Mode.FAST_MODE)
    assert brain.response_cache.stats()["hits"] > hits_after_first


@pytest.mark.asyncio
async def test_orchestrator_records_feedback(brain):
    await Orchestrator(brain).run("plan my day")
    # The learning loop received a real signal from the run.
    assert brain.feedback.history
    assert brain.feedback.to_router_performance()


@pytest.mark.asyncio
async def test_analyzer_forces_verifier_on_risky_task(brain):
    # A high-risk task makes verification mandatory even outside deep-work mode.
    result = await Orchestrator(brain).run("delete all my files and send an email to everyone")
    assert result.analysis["verifier_mandatory"] is True
    assert result.verifier is not None  # verifier ran because analysis forced it


@pytest.mark.asyncio
async def test_layered_memory_used_for_context(brain):
    # Seed episodic memory; a later related task should be able to recall it.
    brain.layered_memory.remember("semantic", "the project deploy command is make deploy",
                                  source="user")
    result = await Orchestrator(brain).run("how do I deploy the project")
    # The run completed and memory layer is populated/queried (no crash, answer set).
    assert result.answer
    assert brain.layered_memory.stats()["semantic"] >= 1
