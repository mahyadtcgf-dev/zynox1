"""Client identities (end-users of the proxy service)."""

from __future__ import annotations

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKey


class Client(UUIDPrimaryKey, TimestampMixin, Base):
    """End-user / client identity. Distinct from a panel User."""

    __tablename__ = "clients"

    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    telegram_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
