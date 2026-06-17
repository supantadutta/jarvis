"""Phase 3 hardening: expanded SOC content + integration tools through the guard."""
from __future__ import annotations

import pytest

from app.security.permissions import Decision
from app.soc.defensive import (
    build_suricata_rule,
    build_wazuh_rule,
    explain_event_id,
    map_to_attack,
)
from app.tools.base import ToolContext


def _ctx(brain, **kw):
    return ToolContext(
        settings=brain.settings, workspace_root=brain.settings.workspace_root,
        services=brain.service_bundle(), agent_key="soc", model_key="ollama/mistral", **kw,
    )


# --- expanded SOC content ---
def test_new_event_ids_present():
    assert explain_event_id(4740)["name"].startswith("User account locked")
    assert explain_event_id(1102)["category"] == "Log Management"
    assert explain_event_id(4698)["category"] == "Persistence"


def test_new_attack_mappings():
    ids = {t["technique_id"] for t in map_to_attack("attacker created a scheduled task then cleared the log")}
    assert "T1053" in ids
    assert "T1070" in ids


def test_build_suricata_rule():
    rule = build_suricata_rule(msg="Suspicious outbound", dest_port=4444, content="evil", sid=1000009)
    assert rule.startswith("alert tcp")
    assert 'msg:"Suspicious outbound"' in rule and "sid:1000009" in rule


def test_build_wazuh_rule():
    xml = build_wazuh_rule(rule_id=100001, level=10, description="Failed logon spike",
                           if_sid=5716, field_match={"win.system.eventID": "4625"})
    assert '<rule id="100001" level="10">' in xml
    assert "<if_sid>5716</if_sid>" in xml
    assert "4625" in xml


# --- integration tools registered + guarded ---
def test_integration_tools_registered(brain):
    names = set(brain.tools.names())
    for n in ("build_soc_query", "generate_readme", "compose_email_draft",
              "create_calendar_event", "send_email_after_approval",
              "send_whatsapp_after_approval", "trigger_n8n_after_approval"):
        assert n in names, n


@pytest.mark.asyncio
async def test_build_soc_query_tool_auto_allows(brain):
    out = await brain.executor.execute(
        "build_soc_query", {"index": "win", "event_id": 4625, "by_fields": ["src_ip"], "threshold": 5},
        _ctx(brain),
    )
    assert out.decision == Decision.AUTO_ALLOW and out.result.ok
    assert "EventCode=4625" in out.result.output["spl"]


@pytest.mark.asyncio
async def test_generate_readme_tool(brain):
    out = await brain.executor.execute(
        "generate_readme", {"name": "Proj", "features": ["a"]}, _ctx(brain)
    )
    assert out.result.ok and "# Proj" in out.result.output


@pytest.mark.asyncio
async def test_create_calendar_event_tool(brain):
    out = await brain.executor.execute(
        "create_calendar_event",
        {"summary": "Standup", "start": "2026-06-16T09:00:00", "end": "2026-06-16T09:30:00"},
        _ctx(brain),
    )
    assert out.result.ok and out.result.artifacts


@pytest.mark.asyncio
async def test_send_email_requires_approval_and_times_out(brain):
    brain.executor.approval_timeout = 0.05
    out = await brain.executor.execute(
        "send_email_after_approval", {"to": ["a@b.com"], "subject": "s", "body": "b"}, _ctx(brain)
    )
    # HIGH_RISK + credential -> must require approval; unapproved -> aborted.
    assert out.decision == Decision.REQUIRES_APPROVAL
    assert out.approval_id is not None
    assert not out.result.ok


@pytest.mark.asyncio
async def test_send_whatsapp_requires_approval(brain):
    brain.executor.approval_timeout = 0.05
    out = await brain.executor.execute(
        "send_whatsapp_after_approval", {"to": "123", "body": "hi"}, _ctx(brain)
    )
    assert out.decision == Decision.REQUIRES_APPROVAL


def test_new_tools_in_mcp_manifest(brain):
    from app.integrations.mcp import export_tool_manifest

    names = {t["name"] for t in export_tool_manifest(brain.tools)["tools"]}
    assert "build_soc_query" in names and "send_email_after_approval" in names
