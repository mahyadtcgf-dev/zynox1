"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-03

Creates every table defined in ``app.models``. The schema is generated from the
SQLAlchemy metadata rather than hand-written so the migration can never drift
from the models.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from sqlalchemy import inspect
from sqlalchemy.schema import MetaData

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _metadata() -> MetaData:
    # Imported here so Alembic's offline mode does not need a database.
    from app.models import Base

    return Base.metadata


def upgrade() -> None:
    metadata = _metadata()
    bind = op.get_bind()

    # In SQLAlchemy 2.x ``Connection.connection`` is a property, not a callable.
    # Going through the Inspector keeps this correct across versions.
    existing = set(inspect(bind).get_table_names())
    if not existing:
        # Fresh database: create everything in dependency order.
        metadata.create_all(bind=bind, checkfirst=True)
        return

    # Existing database: only add what is missing, never drop or alter.
    missing = [t for t in metadata.sorted_tables if t.name not in existing]
    if missing:
        metadata.create_all(bind=bind, tables=missing, checkfirst=True)


def downgrade() -> None:
    metadata = _metadata()
    metadata.drop_all(bind=op.get_bind(), tables=reversed(metadata.sorted_tables))
