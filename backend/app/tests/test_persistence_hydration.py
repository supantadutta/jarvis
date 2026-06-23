"""DB as source of truth: memory write-through + restart hydration + migrations."""
from __future__ import annotations

import pytest

from app.agents.orchestrator import Orchestrator
from app.config import Settings
from app.services.container import Brain


def _settings(tmp_path) -> Settings:
    s = Settings(
        database_url=f"sqlite:///{tmp_path}/jarvis.db", workspace_root=str(tmp_path / "ws"),
        notes_dir=str(tmp_path / "n"), screenshots_dir=str(tmp_path / "s"),
        audit_dir=str(tmp_path / "a"), chroma_path=str(tmp_path / "c"),
        allow_low_risk_write=True,
    )
    s.ensure_dirs()
    return s


@pytest.mark.asyncio
async def test_memory_and_tasks_survive_restart(tmp_path):
    settings = _settings(tmp_path)

    # First "process": persistence on. Add memory + run a task.
    brain1 = Brain(settings, use_mock=True, persist=True)
    brain1.memory.add("the deploy command is make deploy", collection="semantic", source="user")
    result = await Orchestrator(brain1).run("plan my day")
    assert brain1.memory.count() >= 1
    assert brain1.tasks.get(result.task_id) is not None

    # Second "process": fresh Brain on the SAME DB, then hydrate.
    brain2 = Brain(settings, use_mock=True, persist=True)
    assert brain2.memory.count() == 0  # in-memory starts empty
    info = brain2.hydrate()
    assert info["hydrated"] is True
    assert info["memory"] >= 1
    assert info["tasks"] >= 1
    # The durable state is now back in the runtime cache.
    assert brain2.memory.count() >= 1
    assert brain2.tasks.get(result.task_id) is not None
    assert brain2.memory.search("deploy command", limit=1)


def test_hydrate_noop_when_persistence_off(brain):
    # The default test brain has persistence off.
    assert brain.hydrate() == {"hydrated": False}


def test_memory_writethrough_persists_chunks(tmp_path):
    from sqlmodel import Session, select

    from app.models.tables import MemoryChunk

    brain = Brain(_settings(tmp_path), use_mock=True, persist=True)
    brain.memory.add("a fact about pythons and snakes", collection="semantic")
    with Session(brain._engine) as s:
        rows = s.exec(select(MemoryChunk)).all()
    assert any("pythons" in r.text for r in rows)


def test_alembic_migration_creates_full_schema(tmp_path):
    import sqlite3

    from alembic import command
    from alembic.config import Config

    db = tmp_path / "mig.db"
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db}")
    command.upgrade(cfg, "head")

    con = sqlite3.connect(db)
    tables = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
    assert "alembic_version" in tables
    # All core domain tables exist.
    assert {"tasks", "approvals", "audit_logs", "memory_chunks", "models",
            "credentials_metadata", "workflows"} <= tables
