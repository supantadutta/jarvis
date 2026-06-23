"""Advanced Planner v2 (DAG) + Multi-Agent Execution Graph."""
from __future__ import annotations

import pytest

from app.brain.analyzer import CognitiveTaskAnalyzer
from app.brain.graph import GraphExecutor, NodeStatus
from app.brain.planner_v2 import AdvancedPlanner, Plan, PlanNode


def _plan_for(brain, command):
    analysis = CognitiveTaskAnalyzer().analyze(command)
    return AdvancedPlanner(brain.tools).plan(analysis, strategy="auto"), analysis


# --- planner v2 ---
def test_plan_is_valid_dag(brain):
    plan, _ = _plan_for(brain, "research local LLMs and write a markdown report, verify it")
    assert plan.is_dag()
    assert any(n.id == "reason" for n in plan.nodes)
    # reason depends on gather nodes; produce/verify chain after.
    reason = plan.node("reason")
    assert reason is not None


def test_plan_tool_node_permissions_from_registry(brain):
    plan, _ = _plan_for(brain, "research the latest AI news")
    gather = next((n for n in plan.nodes if n.kind == "tool"), None)
    assert gather is not None
    # web_search is NETWORK_ACCESS in the real registry.
    assert gather.permission in ("NETWORK_ACCESS", "SAFE_READ", "BROWSER_READ")


def test_plan_high_risk_adds_verify(brain):
    plan, analysis = _plan_for(brain, "delete files and send an email, world-class accuracy")
    assert analysis.verifier_mandatory
    assert any(n.id == "verify" for n in plan.nodes)


def test_cycle_is_not_a_dag():
    plan = Plan(goal="x", nodes=[
        PlanNode(id="a", description="a", depends_on=["b"]),
        PlanNode(id="b", description="b", depends_on=["a"]),
    ])
    assert plan.is_dag() is False


# --- execution graph ---
@pytest.fixture
def mock_web(monkeypatch):
    from app.tools.builtin import web

    monkeypatch.setattr(web, "do_search", lambda q, **k: [
        {"title": "T", "url": "https://example.com/x", "snippet": ""}])
    monkeypatch.setattr(web, "do_fetch", lambda url, max_chars=20000: "content")


@pytest.mark.asyncio
async def test_graph_runs_dag_to_completion(brain, mock_web):
    plan, _ = _plan_for(brain, "research local LLMs and reason about them")
    result = await GraphExecutor(brain).run(plan)
    assert result.completed is True
    # reason node ran and produced the final answer.
    assert result.results["reason"].status == NodeStatus.COMPLETED
    assert result.final


@pytest.mark.asyncio
async def test_graph_parallel_gather_then_reason(brain, mock_web):
    # Two skills -> two parallel gather nodes -> reason depends on both.
    analysis = CognitiveTaskAnalyzer().analyze(
        "research AI news and generate a splunk soc detection query")
    plan = AdvancedPlanner(brain.tools).plan(analysis)
    gather_nodes = [n for n in plan.nodes if n.id.startswith("gather_")]
    assert len(gather_nodes) >= 2
    reason = plan.node("reason")
    assert set(reason.depends_on) >= {n.id for n in gather_nodes}
    result = await GraphExecutor(brain).run(plan)
    # reason waited for both gathers.
    assert result.results["reason"].status == NodeStatus.COMPLETED


@pytest.mark.asyncio
async def test_graph_tool_node_goes_through_guard(brain):
    # A tool node that requires approval -> guard returns requires_approval.
    plan = Plan(goal="g", nodes=[PlanNode(
        id="risky", description="risky write", kind="tool",
        tool="browser_click_after_approval", args={"selector": "#x", "domain": "example.com"},
        agent="browser")])
    brain.executor.approval_timeout = 0.05
    result = await GraphExecutor(brain).run(plan)
    assert result.results["risky"].decision == "requires_approval"
    assert result.results["risky"].approval_id is not None


@pytest.mark.asyncio
async def test_graph_partial_recovery_skips_dependents(brain):
    # gather fails (unknown tool) -> reason depending on it is skipped.
    plan = Plan(goal="g", nodes=[
        PlanNode(id="bad", description="bad", kind="tool", tool="read_file",
                 args={"path": "/etc/passwd"}, agent="file"),  # denied by guard
        PlanNode(id="after", description="after", kind="reason", depends_on=["bad"]),
    ])
    result = await GraphExecutor(brain).run(plan)
    assert result.results["bad"].status == NodeStatus.FAILED
    assert result.results["after"].status == NodeStatus.SKIPPED
    assert result.completed is False


@pytest.mark.asyncio
async def test_graph_cancellation(brain, mock_web):
    plan, _ = _plan_for(brain, "research AI and reason")
    ex = GraphExecutor(brain)
    ex.cancel()  # cancel before running
    result = await ex.run(plan)
    assert result.cancelled is True
    assert result.completed is False
