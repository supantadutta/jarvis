"""Shared test fixtures. Everything runs on the MockProvider — no network, no keys."""
from __future__ import annotations

import pytest

from app.config import Settings
from app.services.container import Brain


@pytest.fixture
def settings(tmp_path) -> Settings:
    s = Settings(
        database_url=f"sqlite:///{tmp_path}/test.db",
        workspace_root=str(tmp_path / "workspace"),
        notes_dir=str(tmp_path / "notes"),
        screenshots_dir=str(tmp_path / "shots"),
        audit_dir=str(tmp_path / "audit"),
        chroma_path=str(tmp_path / "chroma"),
        allowed_domains_raw="example.com",
        allow_low_risk_write=True,
    )
    s.ensure_dirs()
    return s


@pytest.fixture
def brain(settings) -> Brain:
    return Brain(settings, use_mock=True)
