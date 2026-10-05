"""Managed proxy services (Xray-core instances)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from app.models import Server, ServiceConfig


from app.models.base import Base, TimestampMixin, UUIDPrimaryKey


class Service(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "services"

    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(nullable=False)

    protocol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    transport: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    # running | stopped | degraded | unknown
    status: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Identifier used by the Xray adapter (config tag / inbound tag).
    tag: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)

    server_id: Mapped[str | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("servers.id", ondelete="SET NULL"), nullable=True
    )

    last_checked_at: Mapped[str | None] = mapped_column(nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    configs: Mapped[list[ServiceConfig]] = relationship(  # noqa: F821  # type: ignore[name-defined]
        "ServiceConfig", back_populates="service", lazy="selectin"
    )
    server: Mapped[Server | None] = relationship(  # noqa: F821  # type: ignore[name-defined]
        "Server", back_populates="services", lazy="selectin"
    )

    __table_args__ = (
        Index("ix_services_status", "status"),
        Index("ix_services_enabled", "enabled"),
        Index("ix_services_protocol_transport", "protocol", "transport"),
    )
