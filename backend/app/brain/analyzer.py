"""Cognitive Task Analyzer (Cognitive Processing Engine v2).

Analyzes a request BEFORE planning and produces a typed, auditable `TaskAnalysis`.
Deterministic-first (keyword heuristics) so it is fast, hermetic, and testable;
an LLM can refine it later without changing the contract. This module never runs
tools or calls the network — it only classifies.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.agents.supervisor import SupervisorAgent
from app.llm.registry import TaskType
from app.model_router.modes import Mode

# Cue tables (centralized, easy to extend).
_PRIVACY_CUES = (
    "password", "secret", "token", "api key", "credential", "private", "personal",
    "my email", "my files", "my documents", "ssn", "bank", "salary", "medical",
)
_RISK_HIGH_CUES = (
    "delete", "remove", "send email", "send message", "purchase", "buy", "pay",
    "install", "uninstall", "format", "wipe", "shutdown", "reboot", "transfer",
    "change password", "change setting", "submit", "deploy to prod",
)
_RISK_MED_CUES = ("write", "create file", "move", "rename", "download", "fill form", "click")
_PARALLEL_CUES = ("compare", "multiple models", "consensus", "debate", "several options", "pros and cons")
_VERIFY_CUES = ("verify", "double-check", "accurate", "world-class", "best possible",
                "maximum accuracy", "deep work", "production", "critical")
_BACKGROUND_CUES = ("monitor", "every day", "schedule", "watch", "long", "large", "batch",
                    "crawl", "index", "scan all")
_FORMAT_CUES = {
    "json": ("json", "as json"),
    "code": ("code", "script", "function", "program"),
    "markdown": ("markdown", "md", "table"),
    "report": ("report", "briefing", "summary doc", "incident report"),
    "query": ("splunk", "spl", "logscale", "sigma", "query", "sql"),
}
_SKILL_CUES = {
    "reasoning": ("why", "explain", "analyze", "reason", "design", "architecture"),
    "coding": ("code", "debug", "refactor", "script", "function"),
    "research": ("research", "find", "look up", "latest", "compare", "learn"),
    "web": ("website", "url", "browser", "internet", "online", "download"),
    "cybersecurity": ("soc", "splunk", "mitre", "incident", "detection", "siem", "alert"),
    "writing": ("write", "draft", "report", "summary", "email"),
    "data": ("csv", "data", "spreadsheet", "metrics", "analyze data"),
}


class TaskAnalysis(BaseModel):
    """Structured, machine-readable analysis of a user request."""

    intent: str
    task_type: str
    risk_level: str = "low"  # none|low|medium|high
    complexity: int = 2  # 1..5
    required_skills: list[str] = Field(default_factory=list)
    required_tools: list[str] = Field(default_factory=list)
    required_models: list[str] = Field(default_factory=list)  # capability hints
    output_format: str = "text"
    privacy_sensitivity: int = 1  # 1..5
    cloud_allowed: bool = True
    background_recommended: bool = False
    parallel_useful: bool = False
    verifier_mandatory: bool = False
    suggested_mode: str = Mode.SINGLE_BEST_MODEL.value
    rationale: str = ""


class CognitiveTaskAnalyzer:
    def __init__(self) -> None:
        self._supervisor = SupervisorAgent()

    def analyze(self, command: str, *, mode_override: str | None = None) -> TaskAnalysis:
        low = (command or "").lower()
        cls = self._supervisor.classify(command)

        privacy = 5 if any(c in low for c in _PRIVACY_CUES) else 1
        cloud_allowed = privacy < 4 and cls.mode != Mode.PRIVATE_MODE
        if mode_override == Mode.PRIVATE_MODE.value:
            cloud_allowed = False

        if any(c in low for c in _RISK_HIGH_CUES):
            risk = "high"
        elif any(c in low for c in _RISK_MED_CUES):
            risk = "medium"
        else:
            risk = "low"

        skills = sorted({s for s, cues in _SKILL_CUES.items() if any(c in low for c in cues)})
        if cls.task_type == TaskType.CODING and "coding" not in skills:
            skills.append("coding")
        if cls.task_type == TaskType.CYBERSECURITY and "cybersecurity" not in skills:
            skills.append("cybersecurity")

        out_format = "text"
        for fmt, cues in _FORMAT_CUES.items():
            if any(c in low for c in cues):
                out_format = fmt
                break

        # Complexity: length + multi-step cues + number of skills.
        complexity = 1
        complexity += 1 if len(command) > 160 else 0
        complexity += 1 if any(w in low for w in (" and ", " then ", "after that", "step by step")) else 0
        complexity += 1 if len(skills) >= 2 else 0
        complexity += 1 if cls.task_type in (TaskType.CODING, TaskType.CYBERSECURITY,
                                             TaskType.DATA_ANALYSIS) else 0
        complexity = max(1, min(5, complexity))

        parallel = any(c in low for c in _PARALLEL_CUES)
        verify = any(c in low for c in _VERIFY_CUES) or risk == "high" or complexity >= 4
        background = any(c in low for c in _BACKGROUND_CUES) or complexity >= 5

        # Capability hints for the router.
        req_models: list[str] = []
        if "coding" in skills:
            req_models.append("coding")
        if complexity >= 3 or "reasoning" in skills:
            req_models.append("reasoning")
        if any(c in low for c in ("image", "screenshot", "photo", "diagram", "picture")):
            req_models.append("vision")

        mode = mode_override or cls.mode.value
        if parallel and mode == Mode.SINGLE_BEST_MODEL.value:
            mode = Mode.PARALLEL_MODE.value

        return TaskAnalysis(
            intent=command.strip()[:200],
            task_type=cls.task_type.value,
            risk_level=risk,
            complexity=complexity,
            required_skills=skills,
            required_tools=[],  # filled by the planner
            required_models=req_models,
            output_format=out_format,
            privacy_sensitivity=privacy,
            cloud_allowed=cloud_allowed,
            background_recommended=background,
            parallel_useful=parallel,
            verifier_mandatory=verify,
            suggested_mode=mode,
            rationale=(
                f"type={cls.task_type.value}; skills={skills}; risk={risk}; "
                f"complexity={complexity}; privacy={privacy}"
            ),
        )
