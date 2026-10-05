"""Client/user configurations (VLESS, VMess, Trojan)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from app.models import Service


from app.models.base import Base, TimestampMixin, UUIDPrimaryKey


class ServiceConfig(UUIDPrimaryKey, TimestampMixin, Base):
    """A client configuration bound to a service."""

    __tablename__ = "service_configs"

    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    uuid: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    protocol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    transport: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    service_id: Mapped[uuid.UUID | None] = mapped_column(  # type: ignore[name-defined]
        PG_UUID(as_uuid=True),
        ForeignKey("services.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Effective connection parameters (validated against the transport).
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(nullable=False)
    path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    sni: Mapped[str | None] = mapped_column(String(255), nullable=True)
    host_header: Mapped[str | None] = mapped_column(String(255), nullable=True)
    flow: Mapped[str | None] = mapped_column(String(64), nullable=True)

    security: Mapped[str] = mapped_column(String(32), default="none", nullable=False)
    tls_server_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    alpn: Mapped[str | None] = mapped_column(String(128), nullable=True)
    allow_insecure: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # xHTTP-specific (mode, extra).
    extra: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Arbitrary metadata (client email, notes, tags).
    metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # type: ignore[assignment,misc]

    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    service: Mapped[Service | None] = relationship(  # noqa: F821  # type: ignore[name-defined]
        "Service", back_populates="configs", lazy="selectin"
    )

    __table_args__ = (
        Index("ix_service_configs_protocol_transport", "protocol", "transport"),
        Index("ix_service_configs_enabled", "enabled"),
        Index("ix_service_configs_expires_at", "expires_at"),
    )
