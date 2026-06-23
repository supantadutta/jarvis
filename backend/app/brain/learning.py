"""Self-Evaluation & Learning Loop (Cognitive Processing Engine v2).

Records rich per-task feedback (verifier/factuality/completeness scores, tool
success rate, model, latency, cost, retries, user correction) and folds it into
the existing EvaluationStore so the Brain Router learns. Does NOT auto-train on
private data — datasets for optional fine-tuning are exported (redacted) only on
demand via app.eval.dataset.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel

from app.eval.evaluations import EvaluationStore
from app.llm.registry import TaskType


class TaskFeedback(BaseModel):
    task_id: str
    model_key: str
    task_type: str
    verifier_score: float = 0.0      # 0..1
    factuality: float = 0.0          # 0..1
    completeness: float = 0.0        # 0..1
    tool_success_rate: float = 1.0   # 0..1
    latency_ms: int = 0
    cost: float = 0.0
    retries: int = 0
    user_corrected: bool = False
    user_satisfied: bool | None = None
    notes: str = ""

    def composite(self) -> float:
        base = (0.4 * self.verifier_score + 0.25 * self.completeness
                + 0.2 * self.factuality + 0.15 * self.tool_success_rate)
        if self.user_satisfied is True:
            base = min(1.0, base + 0.1)
        if self.user_corrected or self.user_satisfied is False:
            base = max(0.0, base - 0.3)
        return round(base, 4)

    def passed(self) -> bool:
        return self.composite() >= 0.6 and not self.user_corrected


@dataclass
class FeedbackLoop:
    evaluations: EvaluationStore
    history: list[TaskFeedback] = field(default_factory=list)

    def record(self, fb: TaskFeedback) -> dict:
        self.history.append(fb)
        try:
            tt = TaskType(fb.task_type)
        except ValueError:
            tt = TaskType.DAILY_ASSISTANT
        stat = self.evaluations.record(
            fb.model_key, tt, passed=fb.passed(), score=fb.composite())
        return {
            "model": fb.model_key, "task_type": tt.value,
            "composite": fb.composite(), "passed": fb.passed(),
            "success_rate": round(stat.success_rate, 3), "samples": stat.samples,
        }

    def leaderboard(self, task_type: str | None = None) -> list[dict]:
        rows = self.evaluations.summary()
        if task_type:
            rows = [r for r in rows if r["task_type"] == task_type]
        return sorted(rows, key=lambda r: (-r["success_rate"], -r["samples"]))

    def to_router_performance(self) -> dict:
        return self.evaluations.to_router_performance()
