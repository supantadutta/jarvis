"""Brain Router v2 (Cognitive Processing Engine v2).

A strategy layer on top of the existing, well-tested `ModelRouter`. It maps a
named routing strategy + a `TaskAnalysis` into a `RoutingRequest` and returns the
ModelRouter's result — so all the hard-constraint/privacy/health guarantees of
the base router are preserved. It NEVER relaxes PRIVATE_MODE or privacy floors.
"""
from __future__ import annotations

from enum import Enum

from app.brain.analyzer import TaskAnalysis
from app.llm.registry import ModelSpec, TaskType
from app.model_router.modes import Mode
from app.model_router.router import (
    CostSetting,
    ModelRouter,
    RoutingRequest,
    RoutingResult,
)


class Strategy(str, Enum):
    FASTEST_GOOD_ENOUGH = "fastest_good_enough"
    BEST_REASONING = "best_reasoning"
    BEST_CODING = "best_coding"
    BEST_PRIVATE = "best_private"
    BEST_SOC = "best_soc"
    CHEAPEST_SAFE = "cheapest_safe"
    ENSEMBLE_CONSENSUS = "ensemble_consensus"
    LOCAL_THEN_CLOUD_ESCALATION = "local_then_cloud_escalation"
    VERIFIER_GATED_ESCALATION = "verifier_gated_escalation"
    LONG_CONTEXT_MODE = "long_context_mode"


def choose_strategy(analysis: TaskAnalysis) -> Strategy:
    """Pick a sensible default strategy from the analysis."""
    if not analysis.cloud_allowed or analysis.privacy_sensitivity >= 4:
        return Strategy.BEST_PRIVATE
    if analysis.task_type == TaskType.CYBERSECURITY.value:
        return Strategy.BEST_SOC
    if analysis.parallel_useful:
        return Strategy.ENSEMBLE_CONSENSUS
    if "coding" in analysis.required_skills:
        return Strategy.BEST_CODING
    if analysis.verifier_mandatory or analysis.complexity >= 4:
        return Strategy.VERIFIER_GATED_ESCALATION
    if analysis.complexity <= 2:
        return Strategy.FASTEST_GOOD_ENOUGH
    return Strategy.BEST_REASONING


def _request_for(strategy: Strategy, analysis: TaskAnalysis) -> RoutingRequest:
    try:
        task_type = TaskType(analysis.task_type)
    except ValueError:
        task_type = TaskType.DAILY_ASSISTANT
    needs_vision = "vision" in analysis.required_models
    base = dict(task_type=task_type, needs_vision=needs_vision,
                privacy_required=2 if analysis.cloud_allowed else 5)

    if strategy == Strategy.FASTEST_GOOD_ENOUGH:
        return RoutingRequest(**base, mode=Mode.FAST_MODE, speed_priority=5,
                              min_reasoning=2, cost_setting=CostSetting.PREFER_LOCAL)
    if strategy == Strategy.BEST_REASONING:
        return RoutingRequest(**base, mode=Mode.DEEP_WORK_MODE, min_reasoning=4,
                              cost_setting=CostSetting.ALLOW_PAID)
    if strategy == Strategy.BEST_CODING:
        return RoutingRequest(**base, mode=Mode.SINGLE_BEST_MODEL, min_coding=4,
                              cost_setting=CostSetting.PREFER_LOCAL)
    if strategy == Strategy.BEST_PRIVATE:
        return RoutingRequest(**{**base, "privacy_required": 5}, mode=Mode.PRIVATE_MODE,
                              cost_setting=CostSetting.FREE_ONLY)
    if strategy == Strategy.BEST_SOC:
        return RoutingRequest(**base, mode=Mode.SINGLE_BEST_MODEL, min_reasoning=3,
                              min_coding=3, cost_setting=CostSetting.PREFER_LOCAL)
    if strategy == Strategy.CHEAPEST_SAFE:
        return RoutingRequest(**base, mode=Mode.COST_SAVER_MODE,
                              cost_setting=CostSetting.FREE_ONLY)
    if strategy == Strategy.ENSEMBLE_CONSENSUS:
        return RoutingRequest(**base, mode=Mode.PARALLEL_MODE, k=3,
                              cost_setting=CostSetting.PREFER_LOCAL)
    if strategy == Strategy.LOCAL_THEN_CLOUD_ESCALATION:
        return RoutingRequest(**{**base, "privacy_required": 1}, mode=Mode.CASCADE_MODE,
                              cost_setting=CostSetting.ALLOW_PAID)
    if strategy == Strategy.VERIFIER_GATED_ESCALATION:
        return RoutingRequest(**{**base, "privacy_required": 1}, mode=Mode.CASCADE_MODE,
                              min_reasoning=4, cost_setting=CostSetting.ALLOW_PAID)
    if strategy == Strategy.LONG_CONTEXT_MODE:
        return RoutingRequest(**base, mode=Mode.SINGLE_BEST_MODEL, min_context=100_000,
                              cost_setting=CostSetting.ALLOW_PAID)
    return RoutingRequest(**base)


class BrainRouter:
    def __init__(self, base_router: ModelRouter | None = None) -> None:
        self.base = base_router or ModelRouter()

    def route(
        self,
        candidates: list[ModelSpec],
        analysis: TaskAnalysis,
        *,
        strategy: Strategy | str | None = None,
        performance: dict | None = None,
    ) -> tuple[Strategy, RoutingResult]:
        strat = (
            Strategy(strategy) if isinstance(strategy, str)
            else (strategy or choose_strategy(analysis))
        )
        if performance is not None:
            self.base.performance = performance
        req = _request_for(strat, analysis)
        return strat, self.base.route(candidates, req)
