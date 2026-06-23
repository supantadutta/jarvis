"""Session guardrails (Cognitive Processing Engine v2).

A global safety budget for autonomous/graph runs: caps total actions, wall-clock
time, and estimated cloud cost, and detects loops/oscillation (the agent
repeating the same action). The Permission Guard still gates *what* may run; this
caps *how much* runs in a session so a confused model can't burn money or spin
forever. Pure and deterministic (no I/O), so it's fully testable.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

# Rough per-call cost units by cost_type (local/free are effectively free).
COST_UNITS = {"local": 0.0, "free": 0.0, "paid": 1.0}


@dataclass
class BudgetExceeded:
    reason: str


@dataclass
class SessionBudget:
    max_actions: int = 25
    max_seconds: float = 120.0
    max_cost: float = 10.0          # in COST_UNITS (paid calls)
    loop_window: int = 4            # how many recent actions to inspect
    loop_repeats: int = 3          # identical actions within window => loop

    actions_used: int = 0
    cost_used: float = 0.0
    _start: float = field(default_factory=time.monotonic)
    _recent: list[str] = field(default_factory=list)

    def check(self) -> BudgetExceeded | None:
        if self.actions_used >= self.max_actions:
            return BudgetExceeded(f"action budget reached ({self.max_actions})")
        if (time.monotonic() - self._start) >= self.max_seconds:
            return BudgetExceeded(f"time budget reached ({self.max_seconds}s)")
        if self.cost_used >= self.max_cost:
            return BudgetExceeded(f"cost budget reached ({self.max_cost})")
        if self._is_looping():
            return BudgetExceeded("loop/oscillation detected (repeated identical actions)")
        return None

    def would_exceed_cost(self, cost_type: str) -> bool:
        return (self.cost_used + COST_UNITS.get(cost_type, 0.5)) > self.max_cost

    def record(self, signature: str, *, cost_type: str = "local") -> None:
        self.actions_used += 1
        self.cost_used += COST_UNITS.get(cost_type, 0.5)
        self._recent.append(signature)
        if len(self._recent) > self.loop_window:
            self._recent = self._recent[-self.loop_window :]

    def _is_looping(self) -> bool:
        if len(self._recent) < self.loop_repeats:
            return False
        # The same action signature appears >= loop_repeats times in the window.
        from collections import Counter

        most = Counter(self._recent).most_common(1)
        return bool(most) and most[0][1] >= self.loop_repeats

    def public(self) -> dict:
        return {
            "actions_used": self.actions_used, "max_actions": self.max_actions,
            "cost_used": round(self.cost_used, 3), "max_cost": self.max_cost,
            "elapsed_s": round(time.monotonic() - self._start, 2),
            "max_seconds": self.max_seconds,
        }
