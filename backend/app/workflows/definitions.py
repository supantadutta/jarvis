"""Seed workflow definitions (Phase 1: definitions + manual run; scheduling Phase 2+)."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class WorkflowDef:
    key: str
    name: str
    trigger: str  # schedule | manual | event
    required_agents: list[str]
    required_tools: list[str]
    risk_level: str
    approval_policy: str  # auto_safe | approve_each | trusted
    output_location: str
    schedule: str | None = None
    rollback: str = "none"
    steps: list[str] = field(default_factory=list)


SEED_WORKFLOWS: list[WorkflowDef] = [
    WorkflowDef(
        key="morning_briefing", name="Morning Briefing", trigger="schedule",
        schedule="0 7 * * *", required_agents=["research", "file", "verifier"],
        required_tools=["search_memory", "open_url_readonly", "create_report_markdown"],
        risk_level="low", approval_policy="auto_safe", output_location="data/notes/briefings",
        steps=["gather allowlisted sources", "summarize", "write report", "verify"],
    ),
    WorkflowDef(
        key="email_draft_replies", name="Check Email & Draft Replies", trigger="manual",
        required_agents=["research", "file"], required_tools=["create_report_markdown"],
        risk_level="high", approval_policy="approve_each", output_location="data/notes/email",
        rollback="drafts only; sending requires HIGH_RISK approval",
        steps=["read inbox (read-only)", "draft replies", "await approval to send"],
    ),
    WorkflowDef(
        key="download_daily_report", name="Download Daily Report", trigger="schedule",
        schedule="0 8 * * *", required_agents=["browser"],
        required_tools=["use_browser_session_after_approval", "browser_download_after_approval"],
        risk_level="high", approval_policy="approve_each", output_location="data/workspace/reports",
        steps=["open dashboard with saved session (approval)", "download report (approval)"],
    ),
    WorkflowDef(
        key="organize_downloads", name="Organize Downloads Folder", trigger="manual",
        required_agents=["file"], required_tools=["organize_folder"],
        risk_level="medium", approval_policy="auto_safe", output_location="Downloads",
        rollback="move files back to parent",
        steps=["dry-run organize", "apply if approved"],
    ),
    WorkflowDef(
        key="soc_shift_summary", name="Create SOC Report", trigger="manual",
        required_agents=["soc", "file", "verifier"], required_tools=["create_report_markdown"],
        risk_level="low", approval_policy="auto_safe", output_location="data/notes/soc",
        steps=["collect shift notes from memory", "draft defensive summary", "verify"],
    ),
    WorkflowDef(
        key="github_readme", name="Generate GitHub README", trigger="manual",
        required_agents=["code", "file"], required_tools=["create_report_markdown", "write_file"],
        risk_level="low", approval_policy="auto_safe", output_location="data/workspace",
        steps=["analyze project", "draft README", "save"],
    ),
    WorkflowDef(
        key="backup_folders", name="Backup Selected Folders", trigger="schedule",
        schedule="0 2 * * *", required_agents=["file", "desktop"], required_tools=["organize_folder"],
        risk_level="medium", approval_policy="approve_each", output_location="data/workspace/backups",
        rollback="backups are copies; originals untouched",
        steps=["copy (never delete) selected folders to backup root"],
    ),
    WorkflowDef(
        key="summarize_new_pdfs", name="Summarize New PDFs", trigger="event",
        required_agents=["file", "research"], required_tools=["search_files", "create_report_markdown"],
        risk_level="low", approval_policy="auto_safe", output_location="data/notes/pdf_summaries",
        steps=["detect new PDFs", "summarize", "store to memory"],
    ),
    WorkflowDef(
        key="daily_study_plan", name="Prepare Daily Study Plan", trigger="schedule",
        schedule="30 6 * * *", required_agents=["planner", "file"], required_tools=["write_note"],
        risk_level="low", approval_policy="auto_safe", output_location="data/notes/study",
        steps=["plan day", "write study note"],
    ),
]


def workflow_public(w: WorkflowDef) -> dict:
    return {
        "key": w.key, "name": w.name, "trigger": w.trigger, "schedule": w.schedule,
        "required_agents": w.required_agents, "required_tools": w.required_tools,
        "risk_level": w.risk_level, "approval_policy": w.approval_policy,
        "output_location": w.output_location, "rollback": w.rollback, "steps": w.steps,
    }
