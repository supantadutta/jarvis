"""Phase 2: workflow engine + health-aware routing + persistence repository."""
from __future__ import annotations

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app.llm.mock_provider import MockProvider
from app.llm.registry import ModelRegistry
from app.services.persistence import (
    count_rows,
    load_task,
    persist_approval,
    persist_audit,
    persist_task,
)


# --- workflow engine ---
@pytest.mark.asyncio
async def test_run_known_workflow_records_run_and_output(brain):
    run = await brain.workflows.run("soc_shift_summary")
    assert run.status == "completed"
    assert run.step_summaries  # each step produced a summary
    assert run.outputs  # a markdown report was written via the tool layer
    assert len(brain.workflows.runs()) == 1


@pytest.mark.asyncio
async def test_run_unknown_workflow_fails_gracefully(brain):
    run = await brain.workflows.run("does_not_exist")
    assert run.status == "failed"
    assert "Unknown workflow" in run.error


def test_scheduler_lists_scheduled_only(brain):
    scheduled = brain.scheduler.scheduled()
    keys = {w["key"] for w in scheduled}
    assert "morning_briefing" in keys          # trigger=schedule
    assert "organize_downloads" not in keys     # trigger=manual


# --- health-aware routing ---
@pytest.mark.asyncio
async def test_available_excludes_unhealthy_providers():
    reg = ModelRegistry()
    healthy = MockProvider(healthy=True)
    unhealthy = MockProvider(healthy=False)
    reg.bind_provider("ollama", healthy)
    reg.bind_provider("groq", unhealthy)
    # enable a groq model + keep ollama enabled
    reg.set_enabled("groq/llama-3.3-70b-versatile", True)
    avail = await reg.available(ttl=0)
    providers = {s.provider for s in avail}
    assert "ollama" in providers
    assert "groq" not in providers  # filtered out as unhealthy


@pytest.mark.asyncio
async def test_health_cache_returns_cached_value():
    reg = ModelRegistry()
    reg.bind_provider("ollama", MockProvider(healthy=True))
    key = "ollama/llama3.1"
    assert await reg.health_cached(key, ttl=60) is True
    # second call hits the cache (same value); just assert it stays True
    assert await reg.health_cached(key, ttl=60) is True


# --- persistence repository ---
def _mem_session() -> Session:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    import app.models.tables  # noqa: F401  (register metadata)

    SQLModel.metadata.create_all(engine)
    return Session(engine)


@pytest.mark.asyncio
async def test_persist_and_load_task(brain):
    from app.agents.orchestrator import Orchestrator

    result = await Orchestrator(brain).run("plan my week")
    task = brain.tasks.get(result.task_id)
    with _mem_session() as session:
        persist_task(session, task)
        loaded = load_task(session, task.id)
        assert loaded is not None
        assert loaded["command"] == "plan my week"
        assert loaded["status"] == "completed"
        assert len(loaded["steps"]) >= 1


def test_persist_audit_and_approval():
    from app.audit.logger import AuditLog
    from app.services.approvals import ApprovalQueue, ApprovalRequest
    from app.models.tables import AuditLogRow, ApprovalRow

    audit = AuditLog()
    entry = audit.record(agent="file", tool="write_note", output_summary="ok", risk="low")
    q = ApprovalQueue()
    appr = q.create(ApprovalRequest(
        task_name="t", requested_action="x", agent="browser", model="m", tool="click",
        account=None, credential=None, risk="medium", what_can_change="page",
        action_preview="click()",
    ))
    q.resolve(appr.id, True)

    with _mem_session() as session:
        persist_audit(session, entry)
        persist_audit(session, entry)  # idempotent
        persist_approval(session, appr)
        assert count_rows(session, AuditLogRow) == 1
        assert count_rows(session, ApprovalRow) == 1
