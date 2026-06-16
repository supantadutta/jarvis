"""Shared application dependencies (the Brain singleton)."""
from __future__ import annotations

from app.config import get_settings
from app.services.container import Brain

_brain: Brain | None = None


def get_brain() -> Brain:
    global _brain
    if _brain is None:
        # The live app persists runtime state to the database; tests inject a
        # mock-backed Brain (persistence off) via set_brain().
        _brain = Brain(get_settings(), persist=True)
    return _brain


def set_brain(brain: Brain) -> None:
    """Used by tests to inject a mock-backed Brain."""
    global _brain
    _brain = brain
