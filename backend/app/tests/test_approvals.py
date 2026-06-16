"""Tests for the approval queue + executor approval flow."""
from __future__ import annotations

import asyncio

import pytest

from app.services.approvals import ApprovalQueue, ApprovalRequest, ApprovalStatus
from app.tools.base import ToolContext


def _req() -> ApprovalRequest:
    return ApprovalRequest(
        task_name="t", requested_action="do thing", agent="browser", model="m",
        tool="browser_click_after_approval", account=None, credential=None,
        risk="medium", what_can_change="page state", action_preview="click(#go)",
    )


def test_create_and_pending():
    q = ApprovalQueue()
    a = q.create(_req())
    assert a.status == ApprovalStatus.PENDING
    assert a.id in [p.id for p in q.pending()]


def test_resolve_approve():
    q = ApprovalQueue()
    a = q.create(_req())
    q.resolve(a.id, True)
    assert a.status == ApprovalStatus.APPROVED
    assert ApprovalQueue.is_granted(a)
    assert q.pending() == []


def test_resolve_deny():
    q = ApprovalQueue()
    a = q.create(_req())
    q.resolve(a.id, False)
    assert a.status == ApprovalStatus.DENIED
    assert not ApprovalQueue.is_granted(a)


def test_trust_workflow():
    q = ApprovalQueue()
    a = q.create(_req())
    q.resolve(a.id, True, trust=True)
    assert a.status == ApprovalStatus.TRUSTED
    assert ApprovalQueue.is_granted(a)


@pytest.mark.asyncio
async def test_wait_resolves_when_approved():
    q = ApprovalQueue()
    a = q.create(_req())

    async def approve_soon():
        await asyncio.sleep(0.01)
        q.resolve(a.id, True)

    asyncio.create_task(approve_soon())
    resolved = await q.wait(a.id, timeout=1.0)
    assert ApprovalQueue.is_granted(resolved)


@pytest.mark.asyncio
async def test_wait_times_out_to_expired():
    q = ApprovalQueue()
    a = q.create(_req())
    resolved = await q.wait(a.id, timeout=0.02)
    assert resolved.status == ApprovalStatus.EXPIRED


@pytest.mark.asyncio
async def test_executor_proceeds_after_external_approval(brain):
    ctx = ToolContext(
        settings=brain.settings, workspace_root=brain.settings.workspace_root,
        services=brain.service_bundle(), agent_key="desktop", model_key="ollama/mistral",
    )

    async def approve_when_pending():
        for _ in range(200):
            pend = brain.approvals.pending()
            if pend:
                brain.approvals.resolve(pend[0].id, True)
                return
            await asyncio.sleep(0.005)

    brain.executor.approval_timeout = 2.0
    task = asyncio.create_task(approve_when_pending())
    outcome = await brain.executor.execute("take_desktop_screenshot", {}, ctx)
    await task
    # Approval granted -> tool runs (then fails only because mss isn't installed).
    assert outcome.approval_id is not None
    assert outcome.decision.value == "requires_approval"
