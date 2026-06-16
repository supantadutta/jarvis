"""Phase 2: cascade / cost-saver escalation and specialist-team fan-out.

Driven deterministically by the mock provider, whose verifier fails any answer
containing 'weak' (so escalation can be exercised offline).
"""
from __future__ import annotations

import asyncio

import pytest

from app.agents.orchestrator import Orchestrator
from app.model_router.modes import Mode


@pytest.mark.asyncio
async def test_cascade_stops_at_first_when_verified(brain):
    orch = Orchestrator(brain)
    # No 'weak' marker -> first model passes verification -> single attempt.
    result = await orch.run("summarize this clearly", mode_override=Mode.CASCADE_MODE)
    assert result.mode == Mode.CASCADE_MODE.value
    assert len(result.attempts) == 1
    assert result.verifier and result.verifier["passed"] is True


@pytest.mark.asyncio
async def test_cascade_escalates_when_verifier_fails(brain):
    orch = Orchestrator(brain)
    # 'weak' marker -> every mock answer fails -> escalates through >1 model.
    result = await orch.run("give a weak draft", mode_override=Mode.CASCADE_MODE)
    assert len(result.attempts) >= 2
    assert result.verifier and result.verifier["passed"] is False
    # Cascade should try local/cheap first.
    first = brain.registry.get(result.attempts[0])
    assert first is not None and first.is_local


@pytest.mark.asyncio
async def test_cost_saver_requires_approval_before_paid(brain):
    # Cost-saver escalates locally first; when it reaches a PAID model it must
    # create an approval. With a tiny timeout and no approver, it expires and
    # the cascade stops — but the approval was created (audit trail).
    orch = Orchestrator(brain, approval_timeout=0.05)
    result = await orch.run("produce a weak answer", mode_override=Mode.COST_SAVER_MODE)
    approvals = brain.approvals.all()
    assert any("paid" in a.request.requested_action.lower() for a in approvals)
    # No PAID model was actually used (the paid hop was not granted).
    for key in result.attempts:
        spec = brain.registry.get(key)
        assert spec and spec.cost_type.value != "paid"


@pytest.mark.asyncio
async def test_cost_saver_proceeds_to_paid_when_approved(brain):
    orch = Orchestrator(brain, approval_timeout=2.0)

    async def approve_paid_hops():
        for _ in range(400):
            pend = brain.approvals.pending()
            if pend:
                brain.approvals.resolve(pend[0].id, True)
            await asyncio.sleep(0.005)

    task = asyncio.create_task(approve_paid_hops())
    result = await orch.run("weak weak weak", mode_override=Mode.COST_SAVER_MODE)
    task.cancel()
    # With approvals granted, escalation can reach a paid cloud model.
    assert any(
        (brain.registry.get(k) and brain.registry.get(k).cost_type.value == "paid")
        for k in result.attempts
    )


@pytest.mark.asyncio
async def test_specialist_team_fans_out(brain):
    orch = Orchestrator(brain)
    result = await orch.run(
        "open a website and research the dashboard", mode_override=Mode.SPECIALIST_TEAM_MODE
    )
    assert result.mode == Mode.SPECIALIST_TEAM_MODE.value
    # More than one specialist contributed (e.g. browser + research).
    assert len(result.attempts) >= 2
