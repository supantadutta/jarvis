"""Tests for the tool registry + executor (guard integration)."""
from __future__ import annotations

import pytest

from app.security.permissions import Decision
from app.tools.base import ToolContext


def _ctx(brain, **kw):
    return ToolContext(
        settings=brain.settings,
        workspace_root=brain.settings.workspace_root,
        services=brain.service_bundle(),
        agent_key="file",
        model_key="ollama/mistral",
        **kw,
    )


def test_registry_has_required_tools(brain):
    required = {
        "read_file", "write_file", "write_note", "list_directory", "search_files",
        "organize_folder", "take_desktop_screenshot", "open_url_readonly",
        "browser_get_text", "browser_take_screenshot", "browser_download_after_approval",
        "browser_fill_form_after_approval", "browser_click_after_approval",
        "use_browser_session_after_approval", "propose_terminal_command",
        "run_terminal_readonly_after_approval", "add_memory", "search_memory",
        "create_task", "get_task_status", "request_user_approval",
        "send_telegram_message", "receive_telegram_file", "transcribe_telegram_voice",
        "compare_ai_outputs", "verify_final_answer", "create_report_markdown",
        "create_docx_report", "create_pdf_report",
    }
    names = set(brain.tools.names())
    missing = required - names
    assert not missing, f"missing tools: {missing}"


def test_every_tool_has_permission_and_func(brain):
    for spec in brain.tools.all():
        assert spec.permission is not None
        assert spec.func is not None, f"{spec.name} has no implementation"
        assert spec.description


@pytest.mark.asyncio
async def test_write_note_auto_allowed_creates_file(brain):
    outcome = await brain.executor.execute(
        "write_note", {"title": "hello", "content": "world"}, _ctx(brain)
    )
    assert outcome.result.ok
    assert outcome.decision == Decision.AUTO_ALLOW


@pytest.mark.asyncio
async def test_read_file_roundtrip_and_untrusted_wrapping(brain):
    await brain.executor.execute("write_file", {"path": "a.txt", "content": "secret-data"}, _ctx(brain))
    outcome = await brain.executor.execute("read_file", {"path": "a.txt"}, _ctx(brain))
    assert outcome.result.ok
    assert "untrusted_external_data" in outcome.result.output


@pytest.mark.asyncio
async def test_read_file_outside_workspace_denied(brain):
    outcome = await brain.executor.execute("read_file", {"path": "/etc/passwd"}, _ctx(brain))
    assert outcome.decision == Decision.DENY
    assert not outcome.result.ok


@pytest.mark.asyncio
async def test_browser_read_blocked_by_domain_allowlist(brain):
    outcome = await brain.executor.execute(
        "open_url_readonly", {"url": "http://evil.com", "domain": "evil.com"}, _ctx(brain)
    )
    assert outcome.decision == Decision.DENY


@pytest.mark.asyncio
async def test_browser_write_requires_approval_and_times_out(brain):
    brain.executor.approval_timeout = 0.05
    outcome = await brain.executor.execute(
        "browser_click_after_approval",
        {"selector": "#go", "domain": "example.com"},
        _ctx(brain),
    )
    assert outcome.decision == Decision.REQUIRES_APPROVAL
    assert outcome.approval_id is not None
    assert not outcome.result.ok  # not approved -> aborted


@pytest.mark.asyncio
async def test_emergency_stop_denies_writes(brain):
    brain.set_emergency_stop(True)
    outcome = await brain.executor.execute("write_note", {"title": "x", "content": "y"}, _ctx(brain))
    assert outcome.decision == Decision.DENY


@pytest.mark.asyncio
async def test_organize_folder_dry_run_default(brain):
    # create a file in workspace, then dry-run organize
    await brain.executor.execute("write_file", {"path": "f.log", "content": "x"}, _ctx(brain))
    outcome = await brain.executor.execute("organize_folder", {"path": ".", "dry_run": True}, _ctx(brain))
    assert outcome.result.ok
    assert "Would move" in outcome.result.summary
