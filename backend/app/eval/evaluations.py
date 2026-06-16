"""Self-evaluation loop (Phase 4).

Records per-(model, task_type) outcomes (from Verifier verdicts or explicit
feedback) and exposes a rolling success rate the Model Router consumes as
`performance`. This closes the learning loop sketched in `model_router.md` and
backs the `model_evaluations` table.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.llm.registry import TaskType


@dataclass
class EvalStat:
    model_key: str
    task_type: TaskType
    successes: int = 0
    samples: int = 0
    score_sum: float = 0.0

    @property
    def success_rate(self) -> float:
        return self.successes / self.samples if self.samples else 0.0

    @property
    def avg_score(self) -> float:
        return self.score_sum / self.samples if self.samples else 0.0


class EvaluationStore:
    def __init__(self) -> None:
        self._stats: dict[tuple[str, TaskType], EvalStat] = {}

    def record(self, model_key: str, task_type: TaskType, *, passed: bool, score: float = 0.0) -> EvalStat:
        key = (model_key, task_type)
        stat = self._stats.get(key)
        if stat is None:
            stat = EvalStat(model_key=model_key, task_type=task_type)
            self._stats[key] = stat
        stat.samples += 1
        stat.successes += 1 if passed else 0
        stat.score_sum += score
        return stat

    def get(self, model_key: str, task_type: TaskType) -> EvalStat | None:
        return self._stats.get((model_key, task_type))

    def to_router_performance(self) -> dict[tuple[str, TaskType], float]:
        """The (model, task) -> success_rate map the router scores on."""
        return {k: s.success_rate for k, s in self._stats.items() if s.samples > 0}

    def summary(self) -> list[dict]:
        return [
            {
                "model": s.model_key,
                "task_type": s.task_type.value,
                "samples": s.samples,
                "success_rate": round(s.success_rate, 3),
                "avg_score": round(s.avg_score, 3),
            }
            for s in sorted(self._stats.values(), key=lambda s: (-s.samples, s.model_key))
        ]
