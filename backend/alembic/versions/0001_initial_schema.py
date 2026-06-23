"""initial schema (all 25 tables from the SQLModel metadata)

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-23

This baseline creates the full schema from the SQLModel metadata so the schema is
migration-managed. Subsequent revisions should use op.* operations / autogenerate.
"""
from __future__ import annotations

from alembic import op

import app.models.tables  # noqa: F401 - registers tables on the metadata
from sqlmodel import SQLModel

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    SQLModel.metadata.create_all(op.get_bind())


def downgrade() -> None:
    SQLModel.metadata.drop_all(op.get_bind())
