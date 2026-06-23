"""Autonomous agent loop: reason -> act (guard-gated) -> observe -> repeat."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.deps import set_brain
from app.main import create_app


@pytest.fixture
def mock_web(monkeypatch):
    from app.tools.builtin import web

    monkeypatch.setattr(web, "do_search", lambda q, **k: [
        {"title": "AI", "url": "https://example.com/ai", "snippet": ""},
    ])
    monkeypatch.setattr(web, "do_fetch",
                        lambda url, max_chars=20000: "AI is the simulation of intelligence.")


@pytest.mark.asyncio
async def test_agent_runs_multi_step_then_finishes(brain, mock_web):
    # Script the model: search the web, then write a note, then finish.
    brain._mock.agent_script = [
        {"action": "tool", "tool": "web_search", "args": {"query": "what is AI"},
         "thought": "find info"},
        {"action": "tool", "tool": "write_note",
         "args": {"title": "ai", "content": "AI summary"}, "thought": "save it"},
        {"action": "final", "answer": "Saved an AI note after researching."},
    ]
    result = await brain.autonomous.run("research AI and save a note", max_steps=6)
    assert result.completed is True
    assert "Saved an AI note" in result.answer
    tools_used = [s.tool for s in result.steps]
    assert tools_used == ["web_search", "write_note"]
    assert all(s.ok for s in result.steps)


@pytest.mark.asyncio
async def test_agent_risky_step_requires_approval(brain):
    # The agent tries a browser write (BROWSER_WRITE) -> guard requires approval.
    brain.executor.approval_timeout = 0.05
    brain._mock.agent_script = [
        {"action": "tool", "tool": "write_file", "args": {"path": "x.txt", "content": "hi"},
         "thought": "write"},
        {"action": "final", "answer": "done"},
    ]
    # Disable auto low-risk-write so write_file needs approval.
    brain.apply_policy_update({"allow_low_risk_write": False})
    result = await brain.autonomous.run("write a file", max_steps=4)
    # The write step needed approval (and timed out, unapproved).
    step = result.steps[0]
    assert step.decision == "requires_approval"
    assert step.approval_id is not None


@pytest.mark.asyncio
async def test_agent_rejects_unlisted_tool(brain):
    brain._mock.agent_script = [
        {"action": "tool", "tool": "delete_everything", "args": {}, "thought": "nope"},
        {"action": "final", "answer": "ok"},
    ]
    result = await brain.autonomous.run("do something", max_steps=3,
                                        allowed_tools=["web_search"])
    assert result.steps[0].decision == "deny"
    assert "not allowed" in result.steps[0].observation


@pytest.mark.asyncio
async def test_agent_budget_exhaustion(brain, mock_web):
    # Always search, never finish -> hits the budget.
    brain._mock.agent_script = [
        {"action": "tool", "tool": "web_search", "args": {"query": "x"}} for _ in range(10)
    ]
    result = await brain.autonomous.run("loop forever", max_steps=3)
    assert result.completed is False
    assert len(result.steps) == 3
    assert "step budget" in result.answer


def test_agent_run_endpoint(brain, mock_web):
    set_brain(brain)
    brain._mock.agent_script = [
        {"action": "tool", "tool": "web_search", "args": {"query": "ai"}},
        {"action": "final", "answer": "researched"},
    ]
    with TestClient(create_app()) as c:
        r = c.post("/api/agent/run", json={"goal": "research ai", "max_steps": 4})
        assert r.status_code == 200
        body = r.json()
        assert body["completed"] is True
        assert body["steps"][0]["tool"] == "web_search"
