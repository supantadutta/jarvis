"""Lightweight in-process metrics (Prometheus text exposition).

No external dependency. Counters are incremented from middleware/hot paths;
live gauges are pulled from the Brain at scrape time. Rendered in Prometheus
text format at /api/metrics.
"""
from __future__ import annotations

import threading
from collections import defaultdict


class Metrics:
    def __init__(self) -> None:
        self._counters: dict[tuple[str, tuple], float] = defaultdict(float)
        self._lock = threading.Lock()

    @staticmethod
    def _key(name: str, labels: dict) -> tuple[str, tuple]:
        return name, tuple(sorted(labels.items()))

    def inc(self, name: str, value: float = 1.0, **labels) -> None:
        with self._lock:
            self._counters[self._key(name, labels)] += value

    def snapshot(self) -> list[tuple[str, dict, float]]:
        with self._lock:
            return [(n, dict(lbls), v) for (n, lbls), v in self._counters.items()]

    def render(self, extra_gauges: dict | None = None) -> str:
        lines: list[str] = []
        # Counters (sort by name then label pairs; dicts aren't orderable).
        ordered = sorted(self.snapshot(), key=lambda t: (t[0], tuple(sorted(t[1].items()))))
        for name, labels, value in ordered:
            lbl = ("{" + ",".join(f'{k}="{v}"' for k, v in labels.items()) + "}") if labels else ""
            lines.append(f"{name}{lbl} {value}")
        # Live gauges.
        for name, value in (extra_gauges or {}).items():
            lines.append(f"{name} {value}")
        return "\n".join(lines) + "\n"


METRICS = Metrics()
