"""Model Router — pure, typed, deterministic model selection.

Given a RoutingRequest and a set of candidate ModelSpecs, the router applies
hard-constraint filters (privacy, context, tools, vision, mode) then scores the
survivors and selects one (or k, for multi-model modes). No LLM or I/O here, so
it is fully unit-testable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from app.llm.registry import CostType, ModelSpec, TaskType
from app.model_router.modes import LOCAL_ONLY_MODES, MULTI_MODEL_MODES, Mode


class CostSetting(str, Enum):
    FREE_ONLY = "free_only"
    PREFER_LOCAL = "prefer_local"
    ALLOW_PAID = "allow_paid"


CODE_TASKS = {TaskType.CODING, TaskType.CYBERSECURITY, TaskType.DATA_ANALYSIS}


@dataclass
class RoutingRequest:
    task_type: TaskType = TaskType.DAILY_ASSISTANT
    mode: Mode = Mode.SINGLE_BEST_MODEL
    privacy_required: int = 1  # minimum privacy_level the data demands (1..5)
    min_reasoning: int = 0
    min_coding: int = 0
    speed_priority: int = 2  # 0..5, higher => prefer faster
    cost_setting: CostSetting = CostSetting.PREFER_LOCAL
    min_context: int = 0
    needs_tools: bool = False
    needs_vision: bool = False
    k: int = 3  # how many models for multi-model modes


@dataclass
class ScoredModel:
    spec: ModelSpec
    score: float
    reasons: list[str] = field(default_factory=list)


@dataclass
class RoutingResult:
    selected: list[ModelSpec]
    scored: list[ScoredModel]
    mode: Mode
    rejected: dict[str, str] = field(default_factory=dict)  # key -> reason

    @property
    def primary(self) -> ModelSpec | None:
        return self.selected[0] if self.selected else None


def _mode_weights(mode: Mode) -> dict[str, float]:
    base = {
        "reason": 2.0,
        "code": 2.0,
        "speed": 1.0,
        "privacy": 1.0,
        "task": 1.5,
        "cost": 1.0,
        "perf": 1.0,
    }
    if mode == Mode.FAST_MODE:
        base.update({"speed": 3.0, "reason": 1.0, "privacy": 1.5})
    elif mode == Mode.DEEP_WORK_MODE:
        base.update({"reason": 3.0, "task": 2.0, "speed": 0.5})
    elif mode == Mode.PRIVATE_MODE:
        base.update({"privacy": 3.0})
    elif mode == Mode.COST_SAVER_MODE:
        base.update({"cost": 2.5, "privacy": 1.5})
    return base


def _cost_penalty(cost_type: CostType, setting: CostSetting) -> float:
    if cost_type == CostType.LOCAL:
        return 0.0
    if cost_type == CostType.FREE:
        return 0.5 if setting == CostSetting.ALLOW_PAID else 1.0
    # PAID
    if setting == CostSetting.ALLOW_PAID:
        return 1.0
    return 5.0  # strongly discouraged when not allowing paid


class ModelRouter:
    def __init__(self, *, performance: dict[tuple[str, TaskType], float] | None = None) -> None:
        # performance maps (model_key, task_type) -> success rate in [0,1].
        self.performance = performance or {}

    def _passes_hard(
        self, spec: ModelSpec, req: RoutingRequest
    ) -> tuple[bool, str | None]:
        local_only = req.mode in LOCAL_ONLY_MODES or req.cost_setting == CostSetting.FREE_ONLY
        if local_only and spec.cost_type == CostType.PAID:
            return False, "paid model excluded (local-only/free-only)"
        if req.mode == Mode.PRIVATE_MODE and not spec.is_local:
            return False, "non-local model excluded in PRIVATE_MODE"
        if spec.privacy_level < req.privacy_required:
            return False, f"privacy {spec.privacy_level} < required {req.privacy_required}"
        if req.min_context and spec.max_context < req.min_context:
            return False, f"context {spec.max_context} < required {req.min_context}"
        if req.needs_tools and not spec.tool_calling_support:
            return False, "no tool-calling support"
        if req.needs_vision and not spec.vision_support:
            return False, "no vision support"
        if req.min_reasoning and spec.reasoning_level < req.min_reasoning:
            return False, f"reasoning {spec.reasoning_level} < required {req.min_reasoning}"
        if req.min_coding and spec.coding_level < req.min_coding:
            return False, f"coding {spec.coding_level} < required {req.min_coding}"
        return True, None

    def _score(self, spec: ModelSpec, req: RoutingRequest, w: dict[str, float]) -> ScoredModel:
        reasons: list[str] = []
        score = 0.0

        score += w["reason"] * spec.reasoning_level
        if req.task_type in CODE_TASKS:
            score += w["code"] * spec.coding_level
            reasons.append(f"coding+{w['code'] * spec.coding_level:.1f}")
        score += w["speed"] * spec.speed_level * (req.speed_priority / 5.0)
        score += w["privacy"] * spec.privacy_level

        if req.task_type in spec.task_affinity:
            score += w["task"] * 5.0
            reasons.append(f"task-affinity+{w['task'] * 5.0:.1f}")

        penalty = w["cost"] * _cost_penalty(spec.cost_type, req.cost_setting)
        score -= penalty
        if penalty:
            reasons.append(f"cost-{penalty:.1f}")

        perf = self.performance.get((spec.key, req.task_type))
        if perf is not None:
            score += w["perf"] * perf * 5.0
            reasons.append(f"perf+{w['perf'] * perf * 5.0:.1f}")

        return ScoredModel(spec=spec, score=round(score, 3), reasons=reasons)

    @staticmethod
    def _tie_key(sm: ScoredModel) -> tuple:
        # Higher score; then higher privacy; then lower cost; then lower fallback_priority.
        cost_rank = {CostType.LOCAL: 0, CostType.FREE: 1, CostType.PAID: 2}[sm.spec.cost_type]
        return (-sm.score, -sm.spec.privacy_level, cost_rank, sm.spec.fallback_priority)

    def route(self, candidates: list[ModelSpec], req: RoutingRequest) -> RoutingResult:
        rejected: dict[str, str] = {}
        survivors: list[ModelSpec] = []
        for spec in candidates:
            if not spec.enabled:
                rejected[spec.key] = "disabled"
                continue
            ok, reason = self._passes_hard(spec, req)
            if ok:
                survivors.append(spec)
            else:
                rejected[spec.key] = reason or "rejected"

        w = _mode_weights(req.mode)
        scored = sorted((self._score(s, req, w) for s in survivors), key=self._tie_key)

        if req.mode in MULTI_MODEL_MODES:
            selected = self._select_diverse([s.spec for s in scored], req.k)
        elif req.mode in (Mode.CASCADE_MODE, Mode.COST_SAVER_MODE):
            # Order local/cheap first for escalation.
            selected = [
                s.spec
                for s in sorted(
                    scored,
                    key=lambda sm: (
                        {CostType.LOCAL: 0, CostType.FREE: 1, CostType.PAID: 2}[sm.spec.cost_type],
                        sm.spec.fallback_priority,
                    ),
                )
            ]
        else:
            selected = [scored[0].spec] if scored else []

        return RoutingResult(selected=selected, scored=scored, mode=req.mode, rejected=rejected)

    @staticmethod
    def _select_diverse(ordered: list[ModelSpec], k: int) -> list[ModelSpec]:
        """Pick up to k, preferring provider diversity but never dropping below k
        when more candidates exist."""
        picked: list[ModelSpec] = []
        seen_providers: set[str] = set()
        for spec in ordered:
            if spec.provider not in seen_providers:
                picked.append(spec)
                seen_providers.add(spec.provider)
            if len(picked) >= k:
                return picked
        # Backfill from remaining if diversity didn't reach k.
        for spec in ordered:
            if spec not in picked:
                picked.append(spec)
            if len(picked) >= k:
                break
        return picked[:k]
