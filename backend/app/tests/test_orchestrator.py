"""End-to-end orchestrator tests across multi-AI modes (mock provider)."""
from __future__ import annotations

import pytest

from app.agents.orchestrator import Orchestrator
from app.model_router.modes import Mode


@pytest.mark.asyncio
async def test_single_best_mode(brain):
    orch = Orchestrator(brain)
    result = await orch.run("Summarize my notes please")
    assert result.answer
    assert result.task_id
    assert result.models
    assert brain.tasks.get(result.task_id).status.value == "completed"


@pytest.mark.asyncio
async def test_private_mode_uses_local_models_only(brain):
    orch = Orchestrator(brain)
    result = await orch.run("private: organize my thoughts")
    assert result.mode == Mode.PRIVATE_MODE.value
    for key in result.models:
        spec = brain.registry.get(key)
        assert spec and spec.is_local


@pytest.mark.asyncio
async def test_deep_work_mode_runs_verifier(brain):
    orch = Orchestrator(brain)
    result = await orch.run("deep work: write a world-class plan")
    assert result.mode == Mode.DEEP_WORK_MODE.value
    assert result.verifier is not None
    assert len(result.models) >= 2


@pytest.mark.asyncio
async def test_parallel_mode_produces_candidates(brain):
    orch = Orchestrator(brain)
    result = await orch.run("compare answers about python vs go")
    assert result.mode in (Mode.PARALLEL_MODE.value, Mode.DEBATE_MODE.value)
    assert len(result.candidates) >= 2


@pytest.mark.asyncio
async def test_fast_mode_skips_plan(brain):
    orch = Orchestrator(brain)
    result = await orch.run("quick: what time is it")
    assert result.mode == Mode.FAST_MODE.value
    assert result.plan == []  # planning skipped in fast mode


@pytest.mark.asyncio
async def test_coding_task_classified_and_routed(brain):
    orch = Orchestrator(brain)
    result = await orch.run("write a python script to parse logs")
    assert result.task_type == "coding"


@pytest.mark.asyncio
async def test_soc_task_classified(brain):
    orch = Orchestrator(brain)
    result = await orch.run("generate a splunk query for failed logons")
    assert result.task_type == "cybersecurity"
    assert "soc" in result.agents
