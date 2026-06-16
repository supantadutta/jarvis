"""Execution modes and natural-language mode detection."""
from __future__ import annotations

from enum import Enum


class Mode(str, Enum):
    SINGLE_BEST_MODEL = "SINGLE_BEST_MODEL"
    CASCADE_MODE = "CASCADE_MODE"
    PARALLEL_MODE = "PARALLEL_MODE"
    SPECIALIST_TEAM_MODE = "SPECIALIST_TEAM_MODE"
    DEBATE_MODE = "DEBATE_MODE"
    VERIFIER_MODE = "VERIFIER_MODE"
    FAST_MODE = "FAST_MODE"
    DEEP_WORK_MODE = "DEEP_WORK_MODE"
    PRIVATE_MODE = "PRIVATE_MODE"
    COST_SAVER_MODE = "COST_SAVER_MODE"


# Modes that must never touch a cloud model.
LOCAL_ONLY_MODES: frozenset[Mode] = frozenset({Mode.PRIVATE_MODE, Mode.FAST_MODE})

# Modes that select more than one model.
MULTI_MODEL_MODES: frozenset[Mode] = frozenset(
    {Mode.PARALLEL_MODE, Mode.DEBATE_MODE, Mode.DEEP_WORK_MODE}
)


def detect_mode(text: str, default: Mode = Mode.SINGLE_BEST_MODEL) -> Mode:
    """Map natural-language cues in a command to an execution mode."""
    low = (text or "").lower()
    # Order matters: most specific / safety-relevant first.
    if any(k in low for k in ("private", "local only", "local-only", "offline")):
        return Mode.PRIVATE_MODE
    if any(
        k in low
        for k in ("deep work", "world-class", "world class", "best possible",
                  "maximum accuracy", "use multiple ai", "use multiple models")
    ):
        return Mode.DEEP_WORK_MODE
    if any(k in low for k in ("compare", "debate", "consensus")):
        return Mode.DEBATE_MODE if "debate" in low else Mode.PARALLEL_MODE
    if any(k in low for k in ("save cost", "cost saver", "cheap", "cost-saver")):
        return Mode.COST_SAVER_MODE
    if any(k in low for k in ("fast", "quick", "do it now", "asap", "hurry")):
        return Mode.FAST_MODE
    if "verify" in low or "double check" in low or "double-check" in low:
        return Mode.VERIFIER_MODE
    return default
