"""Groundedness / factuality proxy + orchestrator integration."""
from __future__ import annotations

import pytest

from app.agents.orchestrator import Orchestrator
from app.brain.groundedness import groundedness_score


def test_supported_answer_scores_high():
    sources = ["The capital of France is Paris. The Eiffel Tower is in Paris."]
    g = groundedness_score("Paris is the capital of France.", sources)
    assert g.score >= 0.9
    assert g.unsupported == []


def test_invented_answer_scores_low():
    sources = ["The capital of France is Paris."]
    g = groundedness_score(
        "The moon is made of cheese and dragons rule Antarctica with quantum lasers.", sources)
    assert g.score < 0.5
    assert g.unsupported


def test_no_evidence_is_neutral_low():
    g = groundedness_score("Some factual claim about widgets here.", [])
    assert g.score == 0.5


def test_empty_answer_is_trivially_grounded():
    g = groundedness_score("", ["anything"])
    assert g.score == 1.0


def test_mixed_support():
    sources = ["Python is a programming language used for data science."]
    answer = "Python is a programming language. It was invented by aliens on Mars."
    g = groundedness_score(answer, sources)
    assert 0.0 < g.score < 1.0
    assert any("aliens" in s.lower() for s in g.unsupported)


@pytest.mark.asyncio
async def test_orchestrator_computes_groundedness_when_memory_present(brain):
    # Seed memory so there is retrievable evidence for the task.
    brain.layered_memory.remember(
        "semantic", "the deploy command for the project is make deploy", source="user")
    result = await Orchestrator(brain).run("how do I deploy the project")
    # memory_context was non-empty -> groundedness computed and fed to feedback.
    assert result.groundedness is not None
    assert "score" in result.groundedness
    # The learning loop received the factuality signal.
    assert brain.feedback.history
    assert 0.0 <= brain.feedback.history[-1].factuality <= 1.0
