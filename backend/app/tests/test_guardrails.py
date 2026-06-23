"""Session guardrails: action/cost/time caps + loop detection (and agent honoring)."""
from __future__ import annotations

import pytest

from app.brain.guardrails import SessionBudget


def test_action_budget():
    b = SessionBudget(max_actions=2)
    assert b.check() is None
    b.record("a")
    b.record("b")
    assert b.check() is not None
    assert "action budget" in b.check().reason


def test_cost_budget():
    b = SessionBudget(max_cost=1.0, max_actions=100)
    b.record("x", cost_type="paid")  # +1.0
    assert b.check() is not None and "cost budget" in b.check().reason


def test_would_exceed_cost():
    b = SessionBudget(max_cost=1.0)
    assert b.would_exceed_cost("local") is False
    b.cost_used = 0.6
    assert b.would_exceed_cost("paid") is True   # 0.6 + 1.0 > 1.0
    assert b.would_exceed_cost("local") is False


def test_loop_detection():
    b = SessionBudget(loop_window=4, loop_repeats=3, max_actions=100)
    for _ in range(3):
        b.record("web_search:[('query','x')]")
    assert b.check() is not None
    assert "loop" in b.check().reason


def test_no_false_loop_for_varied_actions():
    b = SessionBudget(loop_window=4, loop_repeats=3, max_actions=100)
    for sig in ("a", "b", "c", "d"):
        b.record(sig)
    assert b.check() is None


@pytest.mark.asyncio
async def test_agent_stops_on_action_budget(brain):
    # Cap actions at 1; the agent keeps searching but is stopped by the guardrail.
    brain.settings.agent_max_actions = 1
    brain._mock.agent_script = [
        {"action": "tool", "tool": "search_memory", "args": {"query": "x"}} for _ in range(10)
    ]
    result = await brain.autonomous.run("loop", max_steps=10)
    assert result.completed is False
    assert "guardrail" in result.answer
    assert result.budget is not None
    assert len(result.steps) <= 2  # stopped early by the budget


@pytest.mark.asyncio
async def test_agent_stops_on_loop(brain):
    brain.settings.agent_max_actions = 100
    # Same action repeated -> loop detection trips.
    brain._mock.agent_script = [
        {"action": "tool", "tool": "search_memory", "args": {"query": "same"}} for _ in range(10)
    ]
    result = await brain.autonomous.run("repeat", max_steps=10)
    assert result.completed is False
    assert "loop" in result.answer or "guardrail" in result.answer
