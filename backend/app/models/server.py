"""Backend servers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from app.models import Service


from app.models.base import Base, TimestampMixin, UUIDPrimaryKey


class Server(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "servers"

    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    address: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    location: Mapped[str | None] = mapped_column(String(128), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # online | offline | degraded | unknown
    status: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    enabled: Mapped[bool] = mapped_column(default=True, nullable=False)

    # Latest sampled metrics (0-100 for utilization).
    cpu_percent: Mapped[float | None] = mapped_column(nullable=True)
    memory_percent: Mapped[float | None] = mapped_column(nullable=True)
    disk_percent: Mapped[float | None] = mapped_column(nullable=True)

    # Bytes per second.
    network_rx_bps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    network_tx_bps: Mapped[int | None] = mapped_column(Integer, nullable=True)

    uptime_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    services: Mapped[list[Service]] = relationship(  # noqa: F821  # type: ignore[name-defined]
        "Service", back_populates="server", lazy="selectin"
    )
