"""Cognitive Task Analyzer + Brain Router v2."""
from __future__ import annotations

from app.brain.analyzer import CognitiveTaskAnalyzer, TaskAnalysis
from app.brain.router_v2 import BrainRouter, Strategy, choose_strategy
from app.llm.registry import seed_models
from app.model_router.modes import Mode


def A() -> CognitiveTaskAnalyzer:
    return CognitiveTaskAnalyzer()


def test_analysis_is_typed_pydantic():
    res = A().analyze("write a python script to parse logs")
    assert isinstance(res, TaskAnalysis)
    assert res.task_type == "coding"
    assert "coding" in res.required_skills
    assert res.output_format in ("code", "text")


def test_privacy_sensitive_disables_cloud():
    res = A().analyze("read my password vault and summarize my personal files")
    assert res.privacy_sensitivity == 5
    assert res.cloud_allowed is False


def test_high_risk_detected_and_verifier_mandatory():
    res = A().analyze("delete all files in my downloads and send email to my boss")
    assert res.risk_level == "high"
    assert res.verifier_mandatory is True


def test_parallel_useful_for_compare():
    res = A().analyze("compare answers from multiple models about rust vs go")
    assert res.parallel_useful is True
    assert res.suggested_mode == Mode.PARALLEL_MODE.value


def test_background_recommended_for_monitoring():
    res = A().analyze("monitor my downloads folder every day and index all new pdfs")
    assert res.background_recommended is True


def test_soc_skill_detected():
    res = A().analyze("generate a splunk query for failed logons and map to mitre")
    assert res.task_type == "cybersecurity"
    assert "cybersecurity" in res.required_skills


# --- router v2 strategies ---
def _seed():
    specs = seed_models()
    for s in specs:
        s.enabled = True
    return specs


def test_choose_strategy_private_for_sensitive():
    res = A().analyze("summarize my private medical documents")
    assert choose_strategy(res) == Strategy.BEST_PRIVATE


def test_choose_strategy_soc():
    res = A().analyze("write a sigma rule for brute force detection")
    assert choose_strategy(res) == Strategy.BEST_SOC


def test_best_private_routes_to_local_only():
    res = A().analyze("read my private notes")
    strat, routing = BrainRouter().route(_seed(), res)
    assert strat == Strategy.BEST_PRIVATE
    assert routing.selected
    for spec in routing.selected:
        assert spec.is_local


def test_best_coding_picks_high_coding_model():
    res = A().analyze("debug and refactor this python function")
    strat, routing = BrainRouter().route(_seed(), res, strategy="best_coding")
    assert routing.primary is not None
    assert routing.primary.coding_level >= 4


def test_ensemble_consensus_returns_multiple():
    res = A().analyze("compare opinions")
    _, routing = BrainRouter().route(_seed(), res, strategy="ensemble_consensus")
    assert len(routing.selected) >= 2


def test_long_context_mode_filters_small_context():
    res = A().analyze("analyze this very long document")
    _, routing = BrainRouter().route(_seed(), res, strategy="long_context_mode")
    for spec in routing.selected:
        assert spec.max_context >= 100_000
