"""Live event bus + WebSocket timeline."""
from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.deps import set_brain
from app.main import create_app
from app.services.events import EventBus


def test_event_bus_snapshot_and_publish():
    bus = EventBus(history=3)
    for i in range(5):
        bus.publish({"n": i})
    snap = bus.snapshot()
    assert [e["n"] for e in snap] == [2, 3, 4]  # ring buffer keeps last 3


@pytest.mark.asyncio
async def test_event_bus_subscriber_receives():
    bus = EventBus()
    q = bus.subscribe()
    bus.publish({"hello": "world"})
    event = await asyncio.wait_for(q.get(), timeout=1.0)
    assert event["hello"] == "world"
    bus.unsubscribe(q)


def test_audit_feeds_event_bus(brain):
    # The Brain wires audit -> events; an audit record should appear in snapshot.
    brain.audit.record(agent="file", tool="write_note", output_summary="ok", risk="low")
    snap = brain.events.snapshot()
    assert any(e.get("tool") == "write_note" for e in snap)


def test_ws_events_snapshot(brain):
    set_brain(brain)
    # Generate some audit activity first.
    brain.audit.record(agent="supervisor", tool="chat", output_summary="hi", risk="low")
    app = create_app()
    with TestClient(app) as client:
        with client.websocket_connect("/api/ws/events") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "snapshot"
            assert any(e.get("tool") == "chat" for e in msg["events"])
