"""Phase 3: SOC defensive helpers, document generation, integrations."""
from __future__ import annotations

import os
import tempfile
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.deps import set_brain
from app.documents.generators import DocumentModel, Section, generate, render_markdown
from app.integrations.email_calendar import build_ics_event, compose_email_draft
from app.integrations.github import ProjectInfo, build_readme
from app.integrations.n8n import build_webhook_payload
from app.integrations.whatsapp import build_template_message, build_text_message
from app.main import create_app
from app.soc.defensive import (
    DetectionSpec,
    build_logscale_query,
    build_sigma_rule,
    build_splunk_spl,
    explain_event_id,
    map_to_attack,
)


# --- SOC defensive ---
def test_explain_known_and_unknown_event_id():
    assert explain_event_id(4625)["name"] == "Failed logon"
    assert explain_event_id(4625)["known"] is True
    assert explain_event_id(999999)["known"] is False


def test_map_to_attack_detects_techniques():
    techs = map_to_attack("we saw lots of failed logons then RDP lateral movement")
    ids = {t["technique_id"] for t in techs}
    assert "T1110" in ids  # brute force
    assert "T1021" in ids  # remote services


def test_build_splunk_spl_with_threshold():
    spec = DetectionSpec(index="wineventlog", event_id=4625,
                         by_fields=["src_ip"], threshold=10)
    spl = build_splunk_spl(spec)
    assert "index=wineventlog" in spl
    assert "EventCode=4625" in spl
    assert "stats count by src_ip" in spl
    assert "where count >= 10" in spl


def test_build_logscale_query():
    spec = DetectionSpec(event_id=4625, by_fields=["src_ip"], threshold=5)
    q = build_logscale_query(spec)
    assert "EventID=4625" in q
    assert "groupBy" in q


def test_build_sigma_rule_skeleton():
    rule = build_sigma_rule(title="Failed logons", event_id=4625)
    assert rule["detection"]["selection"]["EventID"] == 4625
    assert rule["logsource"]["product"] == "windows"


# --- document generation ---
def test_render_markdown_with_table():
    doc = DocumentModel(
        title="Report", sections=[Section("Intro", "hello", ["a", "b"])],
        table_headers=["k", "v"], table_rows=[[1, 2]],
    )
    md = render_markdown(doc)
    assert "# Report" in md and "## Intro" in md
    assert "- a" in md and "| k | v |" in md


def test_generate_markdown_file():
    doc = DocumentModel(title="T", sections=[Section("S", "body")])
    path = os.path.join(tempfile.mkdtemp(), "out.md")
    out = generate(doc, "md", path)
    assert os.path.exists(out)
    assert "# T" in open(out).read()


def test_generate_docx_and_xlsx_and_pdf_if_available():
    doc = DocumentModel(
        title="T", sections=[Section("S", "body", ["x"])],
        table_headers=["a", "b"], table_rows=[[1, 2], [3, 4]],
    )
    d = tempfile.mkdtemp()
    for fmt, mod in (("docx", "docx"), ("xlsx", "openpyxl"), ("pdf", "reportlab")):
        pytest.importorskip(mod)
        out = generate(doc, fmt, os.path.join(d, f"out.{fmt}"))
        assert os.path.exists(out) and os.path.getsize(out) > 0


# --- integrations (pure builders) ---
def test_build_readme_sections():
    rd = build_readme(ProjectInfo(
        name="Jarvis", description="desc", features=["a", "b"],
        tech_stack=["python"], install_cmds=["pip install -r req.txt"], usage="run it",
    ))
    assert "# Jarvis" in rd and "## Features" in rd and "- a" in rd
    assert "```bash" in rd and "## License" in rd


def test_email_draft_with_signature():
    d = compose_email_draft(to=["a@b.com"], subject="hi", body="hello", signature="Jarvis")
    assert d.to == ["a@b.com"]
    assert d.body.endswith("Jarvis")


def test_build_ics_event_is_valid_vevent():
    ics = build_ics_event(summary="Standup", start=datetime(2026, 6, 16, 9, 0),
                          end=datetime(2026, 6, 16, 9, 30), location="Zoom")
    assert "BEGIN:VEVENT" in ics and "END:VEVENT" in ics
    assert "SUMMARY:Standup" in ics
    assert "DTSTART:20260616T090000Z" in ics


def test_whatsapp_payloads_official_shape():
    text = build_text_message("123", "hi")
    assert text["messaging_product"] == "whatsapp" and text["type"] == "text"
    tmpl = build_template_message("123", "welcome")
    assert tmpl["type"] == "template"


def test_n8n_payload():
    p = build_webhook_payload("backup", {"folder": "x"})
    assert p["source"] == "jarvis" and p["data"]["folder"] == "x"


# --- API endpoints ---
@pytest.fixture
def client(brain):
    set_brain(brain)
    with TestClient(create_app()) as c:
        yield c


def test_api_soc_event(client):
    r = client.get("/api/soc/event/4624")
    assert r.status_code == 200 and r.json()["known"] is True


def test_api_soc_splunk(client):
    r = client.post("/api/soc/splunk", json={"index": "win", "event_id": 4625,
                                             "by_fields": ["src_ip"], "threshold": 5})
    body = r.json()
    assert "EventCode=4625" in body["spl"] and "EventID=4625" in body["logscale"]


def test_api_documents_generate_md(client):
    r = client.post("/api/documents/generate", json={"title": "Doc", "format": "md",
                                                     "content": "hello"})
    assert r.status_code == 200 and r.json()["ok"] is True
    assert os.path.exists(r.json()["path"])


def test_api_readme(client):
    r = client.post("/api/integrations/readme", json={"name": "X", "features": ["f1"]})
    assert "# X" in r.json()["readme"]


def test_api_email_draft_is_draft_only(client):
    r = client.post("/api/integrations/email/draft",
                    json={"to": ["a@b.com"], "subject": "s", "body": "b"})
    body = r.json()
    assert body["draft"]["subject"] == "s"
    assert "approval" in body["note"].lower()


def test_tool_registry_has_xlsx(client):
    names = {t["name"] for t in client.get("/api/tools").json()["tools"]}
    assert "create_xlsx_report" in names
