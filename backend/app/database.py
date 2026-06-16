"""Database engine + session helpers (SQLModel).

Default is SQLite for local-first operation; set DATABASE_URL to a Postgres DSN
for scale-up. `init_db()` creates all tables defined in app.models.tables.
"""
from __future__ import annotations

from collections.abc import Iterator

from sqlmodel import Session, SQLModel, create_engine

from app.config import get_settings

_settings = get_settings()

_connect_args = {"check_same_thread": False} if _settings.database_url.startswith("sqlite") else {}
engine = create_engine(_settings.database_url, echo=False, connect_args=_connect_args)


def init_db() -> None:
    # Import models so they register on SQLModel.metadata before create_all.
    import app.models.tables  # noqa: F401

    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
