"""Safety: cascade/cost-saver escalation respects the attempt budget."""
from __future__ import annotations

import pytest

from app.agents.orchestrator import Orchestrator
from app.model_router.modes import Mode


@pytest.mark.asyncio
async def test_cascade_stops_at_attempt_budget(brain):
    # Every mock answer contains "weak" -> verifier never passes -> would try all
    # models, but the budget caps it.
    brain.settings.max_cascade_attempts = 2
    result = await Orchestrator(brain).run("weak draft please", mode_override=Mode.CASCADE_MODE)
    assert len(result.attempts) <= 2
    assert result.verifier and result.verifier["passed"] is False


@pytest.mark.asyncio
async def test_budget_one_means_single_attempt(brain):
    brain.settings.max_cascade_attempts = 1
    result = await Orchestrator(brain).run("weak", mode_override=Mode.CASCADE_MODE)
    assert len(result.attempts) == 1
