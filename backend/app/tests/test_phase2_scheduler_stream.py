"""Phase 2 (cont.): cron matcher, scheduler, token streaming, voice/scheduler API."""
from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.agents.orchestrator import Orchestrator
from app.deps import set_brain
from app.llm.base import ChatMessage, CompletionRequest, Role, stream_text
from app.llm.mock_provider import MockProvider
from app.main import create_app
from app.model_router.modes import Mode
from app.workflows.cron import cron_match, parse_cron


# --- cron matcher ---
def test_parse_cron_fields():
    fields = parse_cron("*/15 9-17 * * 1-5")
    assert fields[0] == {0, 15, 30, 45}
    assert fields[1] == {9, 10, 11, 12, 13, 14, 15, 16, 17}
    assert fields[4] == {1, 2, 3, 4, 5}  # cron dow: 1-5 = Mon-Fri (0=Sun)


def test_cron_match_specific_minute():
    # 07:00 every day
    assert cron_match("0 7 * * *", datetime(2026, 6, 16, 7, 0))
    assert not cron_match("0 7 * * *", datetime(2026, 6, 16, 7, 1))
    assert not cron_match("0 7 * * *", datetime(2026, 6, 16, 8, 0))


def test_cron_match_weekday():
    # Standard cron dow: 0=Sunday. 2026-06-14 is a Sunday.
    assert cron_match("30 6 * * 0", datetime(2026, 6, 14, 6, 30))
    assert not cron_match("30 6 * * 0", datetime(2026, 6, 15, 6, 30))  # Monday


def test_invalid_cron_raises():
    with pytest.raises(ValueError):
        parse_cron("* * *")


# --- scheduler ---
def test_scheduler_due_matches_morning_briefing(brain):
    # morning_briefing is "0 7 * * *"
    due = brain.scheduler.due(datetime(2026, 6, 16, 7, 0))
    assert "morning_briefing" in due
    assert brain.scheduler.due(datetime(2026, 6, 16, 7, 1)) == []


@pytest.mark.asyncio
async def test_scheduler_run_due_dedups_within_minute(brain):
    now = datetime(2026, 6, 16, 7, 0)
    ran1 = await brain.scheduler.run_due(now)
    ran2 = await brain.scheduler.run_due(now)  # same minute -> no re-run
    assert "morning_briefing" in ran1
    assert ran2 == []
    assert len(brain.workflows.runs()) == len(ran1)


# --- provider token streaming ---
@pytest.mark.asyncio
async def test_mock_provider_stream_reconstructs_text():
    p = MockProvider()
    req = CompletionRequest(model="m", messages=[ChatMessage(Role.USER, "hello world from jarvis")])
    chunks = [c async for c in p.stream(req)]
    assert len(chunks) >= 1
    full = "".join(chunks)
    expected = (await p.complete(req)).text
    assert full == expected


@pytest.mark.asyncio
async def test_stream_text_helper_uses_native_stream():
    p = MockProvider()
    req = CompletionRequest(model="m", messages=[ChatMessage(Role.USER, "abc def ghi")])
    chunks = [c async for c in stream_text(p, req)]
    assert "".join(chunks) == (await p.complete(req)).text


@pytest.mark.asyncio
async def test_orchestrator_stream_answer_single_model(brain):
    events = []
    async for ev, data in Orchestrator(brain).stream_answer("quick hello", mode_override=Mode.FAST_MODE):
        events.append((ev, data))
    names = [e for e, _ in events]
    assert names[0] == "classified"
    assert "routed" in names
    assert names.count("token") >= 1
    assert names[-1] == "done"
    # The streamed task was recorded + completed.
    done = events[-1][1]
    assert brain.tasks.get(done["task_id"]).status.value == "completed"


# --- API: voice + scheduler endpoints ---
@pytest.fixture
def client(brain):
    set_brain(brain)
    with TestClient(create_app()) as c:
        yield c


def test_voice_command_endpoint(client):
    r = client.post("/api/voice/command", json={"message": "summarize my notes"})
    assert r.status_code == 200
    body = r.json()
    assert body["answer"] and body["task_id"]
    assert body["transcript"] == "summarize my notes"


def test_voice_status_endpoint(client):
    r = client.get("/api/voice/status")
    assert r.status_code == 200
    assert "available" in r.json()


def test_scheduler_tick_endpoint(client):
    r = client.post("/api/scheduler/tick")
    assert r.status_code == 200
    assert "ran" in r.json()
