"""Tests for the Model Router selection logic."""
from __future__ import annotations

from app.llm.registry import CostType, ModelSpec, TaskType, seed_models
from app.model_router.modes import Mode
from app.model_router.router import CostSetting, ModelRouter, RoutingRequest


def enabled_seed() -> list[ModelSpec]:
    specs = seed_models()
    for s in specs:  # enable cloud models so filtering logic is exercised
        s.enabled = True
    return specs


def test_private_mode_excludes_cloud():
    router = ModelRouter()
    req = RoutingRequest(mode=Mode.PRIVATE_MODE)
    result = router.route(enabled_seed(), req)
    assert result.selected
    for spec in result.selected:
        assert spec.is_local, f"{spec.key} is not local in PRIVATE_MODE"


def test_free_only_excludes_paid():
    router = ModelRouter()
    req = RoutingRequest(cost_setting=CostSetting.FREE_ONLY)
    result = router.route(enabled_seed(), req)
    for spec in result.selected:
        assert spec.cost_type != CostType.PAID


def test_coding_task_prefers_high_coding_model():
    router = ModelRouter()
    req = RoutingRequest(task_type=TaskType.CODING, min_coding=4, cost_setting=CostSetting.PREFER_LOCAL)
    result = router.route(enabled_seed(), req)
    assert result.primary is not None
    assert result.primary.coding_level >= 4


def test_context_filter_rejects_small_context():
    router = ModelRouter()
    req = RoutingRequest(min_context=500_000)  # only gemini (1M) qualifies among seeds
    result = router.route(enabled_seed(), req)
    for spec in result.selected:
        assert spec.max_context >= 500_000


def test_tool_requirement_filters():
    specs = enabled_seed()
    req = RoutingRequest(needs_tools=True)
    result = ModelRouter().route(specs, req)
    for spec in result.selected:
        assert spec.tool_calling_support


def test_multi_model_modes_return_multiple():
    router = ModelRouter()
    for mode in (Mode.PARALLEL_MODE, Mode.DEBATE_MODE, Mode.DEEP_WORK_MODE):
        result = router.route(enabled_seed(), RoutingRequest(mode=mode, k=3))
        assert len(result.selected) >= 2, mode


def test_provider_diversity_in_parallel():
    router = ModelRouter()
    result = router.route(enabled_seed(), RoutingRequest(mode=Mode.PARALLEL_MODE, k=3))
    providers = [s.provider for s in result.selected]
    assert len(set(providers)) >= 2  # not all the same provider


def test_disabled_models_rejected():
    specs = seed_models()  # cloud ones disabled by default
    result = ModelRouter().route(specs, RoutingRequest(mode=Mode.PRIVATE_MODE))
    assert all(s.provider == "ollama" for s in result.selected)


def test_cascade_orders_local_first():
    router = ModelRouter()
    result = router.route(enabled_seed(), RoutingRequest(mode=Mode.CASCADE_MODE,
                                                         cost_setting=CostSetting.ALLOW_PAID))
    # first should be local
    assert result.selected[0].is_local


def test_performance_history_boosts_score():
    base = ModelRouter()
    boosted = ModelRouter(performance={("ollama/mistral", TaskType.DAILY_ASSISTANT): 1.0})
    req = RoutingRequest(task_type=TaskType.DAILY_ASSISTANT)
    specs = enabled_seed()
    base_scored = {m.spec.key: m.score for m in base.route(specs, req).scored}
    boosted_result = boosted.route(specs, req)
    boosted_scored = {m.spec.key: m.score for m in boosted_result.scored}
    # A perfect history should raise mistral's score, not lower it.
    assert "ollama/mistral" in boosted_scored
    assert boosted_scored["ollama/mistral"] > base_scored["ollama/mistral"]
