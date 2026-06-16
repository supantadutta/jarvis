"""Phase 2 (cont.): write-through persistence, SSE streaming, browser sessions."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.agents.orchestrator import Orchestrator
from app.config import Settings
from app.deps import set_brain
from app.main import create_app
from app.models.tables import AuditLogRow, ChatMessage, TaskRow
from app.services.container import Brain


@pytest.fixture
def persistent_brain(tmp_path) -> Brain:
    s = Settings(
        database_url=f"sqlite:///{tmp_path}/p.db",
        workspace_root=str(tmp_path / "ws"), notes_dir=str(tmp_path / "n"),
        screenshots_dir=str(tmp_path / "sh"), audit_dir=str(tmp_path / "au"),
        chroma_path=str(tmp_path / "ch"), allow_low_risk_write=True,
    )
    s.ensure_dirs()
    return Brain(s, use_mock=True, persist=True)


@pytest.mark.asyncio
async def test_write_through_persists_task_audit_chat(persistent_brain):
    brain = persistent_brain
    result = await Orchestrator(brain).run("plan my day")
    with Session(brain._engine) as s:
        tasks = s.exec(select(TaskRow)).all()
        audits = s.exec(select(AuditLogRow)).all()
        chats = s.exec(select(ChatMessage)).all()
    assert any(t.id == result.task_id and t.status == "completed" for t in tasks)
    assert len(audits) >= 1  # the orchestrator's final audit record landed in DB
    assert len(chats) >= 2   # user + assistant messages persisted


@pytest.mark.asyncio
async def test_write_through_persists_resolved_approval(persistent_brain):
    from app.services.approvals import ApprovalRequest
    from app.models.tables import ApprovalRow

    brain = persistent_brain
    appr = brain.approvals.create(ApprovalRequest(
        task_name="t", requested_action="x", agent="browser", model="m", tool="click",
        account=None, credential=None, risk="medium", what_can_change="page",
        action_preview="click()",
    ))
    brain.approvals.resolve(appr.id, True)
    with Session(brain._engine) as s:
        rows = s.exec(select(ApprovalRow)).all()
    assert any(r.id == appr.id and r.status == "approved" for r in rows)


def test_mock_brain_does_not_persist(brain):
    # Default test brain has persistence off; no engine wired.
    assert brain.persist_enabled is False
    assert brain._engine is None


# --- SSE streaming endpoint ---
@pytest.fixture
def client(brain):
    set_brain(brain)
    with TestClient(create_app()) as c:
        yield c


def test_chat_stream_emits_sse_events(client):
    r = client.post("/api/chat/stream", json={"message": "hello there"})
    assert r.status_code == 200
    assert "text/event-stream" in r.headers["content-type"]
    body = r.text
    assert "event: classified" in body
    assert "event: routed" in body
    assert "event: token" in body
    assert "event: done" in body


# --- encrypted browser session store ---
def test_session_store_roundtrip_encrypted():
    pytest.importorskip("cryptography")
    import os
    import tempfile

    from app.browser.controller import SessionStore
    from app.security.credentials import FernetVault

    key = FernetVault.generate_key()
    path = os.path.join(tempfile.mkdtemp(), "vault.json")
    store = SessionStore(FernetVault(key, store_path=path))
    state = {"cookies": [{"name": "session", "value": "topsecret"}]}
    store.save("gmail", state)
    assert store.load("gmail") == state
    # cookie value must be encrypted at rest
    with open(path) as fh:
        assert "topsecret" not in fh.read()
    store.delete("gmail")
    assert store.load("gmail") is None
