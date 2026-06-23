"""Unified execution engine: one engine, three strategies, shared cross-cutting."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.brain.analyzer import CognitiveTaskAnalyzer
from app.brain.engine import ExecutionKind, UnifiedEngine
from app.deps import set_brain
from app.main import create_app


@pytest.fixture
def mock_web(monkeypatch):
    from app.tools.builtin import web

    monkeypatch.setattr(web, "do_search", lambda q, **k: [
        {"title": "T", "url": "https://example.com/x", "snippet": ""}])
    monkeypatch.setattr(web, "do_fetch", lambda url, max_chars=20000: "evidence content")


def _A(cmd):
    return CognitiveTaskAnalyzer().analyze(cmd)


# --- strategy auto-selection ---
def test_select_chat_for_simple_qa(brain):
    eng = UnifiedEngine(brain)
    assert eng.select(_A("what is the capital of france"), ExecutionKind.AUTO) == ExecutionKind.CHAT


def test_select_autonomous_for_agentic_goal(brain):
    eng = UnifiedEngine(brain)
    kind = eng.select(_A("organize my downloads and then download my report"), ExecutionKind.AUTO)
    assert kind == ExecutionKind.AUTONOMOUS


def test_select_graph_for_multi_skill(brain):
    eng = UnifiedEngine(brain)
    kind = eng.select(_A("research AI news and generate a splunk soc query"), ExecutionKind.AUTO)
    assert kind == ExecutionKind.GRAPH


def test_explicit_execution_overrides(brain):
    eng = UnifiedEngine(brain)
    assert eng.select(_A("anything"), ExecutionKind.GRAPH) == ExecutionKind.GRAPH


# --- the three strategies run through the one engine ---
@pytest.mark.asyncio
async def test_engine_chat_strategy(brain):
    res = await brain.engine.run("what is 2+2", execution="chat")
    assert res.kind == "chat"
    assert res.answer and res.analysis is not None and res.quality is not None


@pytest.mark.asyncio
async def test_engine_autonomous_strategy_uniform_postprocess(brain, mock_web):
    brain._mock.agent_script = [
        {"action": "tool", "tool": "web_search", "args": {"query": "x"}},
        {"action": "final", "answer": "evidence content found and summarized"},
    ]
    res = await brain.engine.run("automate a web search", execution="autonomous")
    assert res.kind == "autonomous"
    # Uniform post-step applied: quality + budget present, feedback recorded.
    assert res.quality is not None
    assert res.budget is not None
    assert brain.feedback.history


@pytest.mark.asyncio
async def test_engine_graph_strategy_shared_budget(brain, mock_web):
    res = await brain.engine.run("research AI and reason about it", execution="graph")
    assert res.kind == "graph"
    assert res.quality is not None
    assert res.budget is not None  # shared SessionBudget reported


@pytest.mark.asyncio
async def test_engine_records_feedback_for_all_strategies(brain, mock_web):
    before = len(brain.feedback.history)
    await brain.engine.run("what is python", execution="chat")
    await brain.engine.run("research python and reason", execution="graph")
    assert len(brain.feedback.history) > before  # learning fed uniformly


# --- single API entry point ---
def test_brain_run_endpoint_auto_selects(brain, mock_web):
    set_brain(brain)
    with TestClient(create_app()) as c:
        r = c.post("/api/brain/run", json={"command": "what is the capital of france"})
        assert r.status_code == 200
        body = r.json()
        assert body["kind"] in ("chat", "autonomous", "graph")
        assert body["answer"]
        assert "analysis" in body and "quality" in body


def test_brain_run_explicit_autonomous(brain, mock_web):
    set_brain(brain)
    brain._mock.agent_script = [{"action": "final", "answer": "done"}]
    with TestClient(create_app()) as c:
        r = c.post("/api/brain/run", json={"command": "do a thing", "execution": "autonomous"})
        assert r.json()["kind"] == "autonomous"
