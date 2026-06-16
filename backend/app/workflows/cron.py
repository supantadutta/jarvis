"""Minimal cron expression matcher (pure, dependency-free).

Supports the standard 5-field format: `minute hour day-of-month month day-of-week`
with `*`, single values, comma lists (`1,15`), ranges (`1-5`), and steps
(`*/5`, `10-30/5`). Enough for workflow scheduling without pulling in a cron
library; swap for croniter/APScheduler if richer semantics are needed.
"""
from __future__ import annotations

from datetime import datetime

# (min, max) inclusive bounds per field.
# day-of-week uses the standard cron convention: 0=Sunday .. 6=Saturday.
_BOUNDS = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 6)]


def _parse_field(field: str, lo: int, hi: int) -> set[int]:
    values: set[int] = set()
    for part in field.split(","):
        step = 1
        if "/" in part:
            base, step_s = part.split("/", 1)
            step = int(step_s)
        else:
            base = part
        if base in ("*", ""):
            start, end = lo, hi
        elif "-" in base:
            a, b = base.split("-", 1)
            start, end = int(a), int(b)
        else:
            start = end = int(base)
        for v in range(start, end + 1, step):
            if lo <= v <= hi:
                values.add(v)
    return values


def parse_cron(expr: str) -> list[set[int]]:
    fields = expr.split()
    if len(fields) != 5:
        raise ValueError(f"cron expression must have 5 fields, got {len(fields)}: {expr!r}")
    return [_parse_field(f, lo, hi) for f, (lo, hi) in zip(fields, _BOUNDS, strict=True)]


def cron_match(expr: str, dt: datetime) -> bool:
    """True if `dt` (minute granularity) satisfies the cron expression."""
    minute, hour, dom, month, dow = parse_cron(expr)
    # Convert Python weekday() (Mon=0..Sun=6) to cron dow (Sun=0..Sat=6).
    cron_dow = (dt.weekday() + 1) % 7
    return (
        dt.minute in minute
        and dt.hour in hour
        and dt.day in dom
        and dt.month in month
        and cron_dow in dow
    )
