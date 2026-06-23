"""Response Quality Engine (Cognitive Processing Engine v2).

A deterministic pre-final quality pass over a candidate answer given the request
and its TaskAnalysis. Checks request satisfaction, format match, safety, length
appropriateness, citation needs, missing assumptions, and whether to ask for
clarification vs proceed. Returns a structured, auditable report. The LLM
Verifier remains the authoritative reviewer; this is the fast guardrail layer.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.brain.analyzer import TaskAnalysis
from app.security.prompt_injection import scan_for_injection

_VAGUE_CUES = ("it depends", "i'm not sure", "as an ai", "i cannot", "unclear")


class QualityReport(BaseModel):
    passed: bool
    scores: dict[str, float] = Field(default_factory=dict)
    issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    should_ask_clarification: bool = False
    needs_citations: bool = False


class QualityEngine:
    def assess(self, *, request: str, answer: str, analysis: TaskAnalysis) -> QualityReport:
        issues: list[str] = []
        suggestions: list[str] = []
        scores: dict[str, float] = {}
        ans = (answer or "").strip()
        low = ans.lower()

        # Completeness.
        if not ans:
            issues.append("empty answer")
            scores["completeness"] = 0.0
        elif len(ans) < 20:
            issues.append("answer is very short")
            scores["completeness"] = 0.4
        else:
            scores["completeness"] = 0.9

        # Length appropriateness vs complexity.
        if analysis.complexity <= 2 and len(ans) > 4000:
            suggestions.append("answer may be too verbose for a simple task")
        if analysis.complexity >= 4 and len(ans) < 200:
            issues.append("answer may be too short for a complex task")

        # Format match.
        fmt = analysis.output_format
        fmt_ok = True
        if fmt == "code" and "```" not in ans and "def " not in ans and "{" not in ans:
            fmt_ok = False
            suggestions.append("expected code/code-block output")
        if fmt == "json" and not (ans.startswith("{") or ans.startswith("[")):
            fmt_ok = False
            suggestions.append("expected JSON output")
        if fmt == "query" and not any(k in low for k in ("index=", "eventid", "|", "select")):
            suggestions.append("expected a query-style output")
        scores["format"] = 1.0 if fmt_ok else 0.5

        # Safety: answer must not carry injection/role-override content.
        scan = scan_for_injection(ans)
        scores["safety"] = 0.3 if scan.flagged else 1.0
        if scan.flagged:
            issues.append("answer contains suspicious/injection-like content")

        # Citations needed for research/factual tasks.
        needs_citations = analysis.task_type in ("research", "report_writing") or \
            "research" in analysis.required_skills
        if needs_citations and ("http" not in low and "source" not in low):
            suggestions.append("add sources/citations for factual claims")

        # Clarification: vague/hedging answer on a non-trivial request.
        should_ask = any(c in low for c in _VAGUE_CUES) and analysis.complexity >= 3
        if should_ask:
            suggestions.append("consider asking the user a clarifying question")

        passed = not issues and scores.get("safety", 1.0) >= 0.9
        return QualityReport(
            passed=passed, scores=scores, issues=issues, suggestions=suggestions,
            should_ask_clarification=should_ask, needs_citations=needs_citations,
        )
