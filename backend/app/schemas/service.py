"""Service and server schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import ORMModel, validate_host
from app.schemas.transports import ProtocolType, TransportType


class ServiceBase(BaseModel):
    model_config = {"str_strip_whitespace": True, "extra": "forbid"}

    name: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2048)
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(ge=1, le=65535)
    protocol: ProtocolType
    transport: TransportType
    tag: str | None = Field(default=None, max_length=128)
    server_id: uuid.UUID | None = None

    @field_validator("host")
    @classmethod
    def _host(cls, v: str) -> str:
        return validate_host(v)

    @field_validator("tag")
    @classmethod
    def _tag(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v or None


class ServiceCreateIn(ServiceBase):
    enabled: bool = True


class ServiceUpdateIn(BaseModel):
    model_config = {"str_strip_whitespace": True, "extra": "forbid"}

    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2048)
    host: str | None = Field(default=None, min_length=1, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    protocol: ProtocolType | None = None
    transport: TransportType | None = None
    tag: str | None = Field(default=None, max_length=128)
    server_id: uuid.UUID | None = None
    enabled: bool | None = None


class ServiceOut(ORMModel):
    id: uuid.UUID
    name: str
    description: str | None = None
    host: str
    port: int
    protocol: str
    transport: str
    tag: str | None = None
    status: str
    enabled: bool
    server_id: uuid.UUID | None = None
    last_error: str | None = None
    config_count: int = 0
    created_at: datetime
    updated_at: datetime


class ServiceActionIn(BaseModel):
    """Predefined safe action — never a free-form command."""

    action: str = Field(pattern="^(start|stop|restart|reload|test)$")


class ServiceActionOut(BaseModel):
    action: str
    status: str
    message: str
    duration_ms: int


class ServiceLogOut(BaseModel):
    level: str
    message: str
    timestamp: datetime | None = None


# ── Servers ──────────────────────────────────────────────────


class ServerBase(BaseModel):
    model_config = {"str_strip_whitespace": True, "extra": "forbid"}

    name: str = Field(min_length=1, max_length=128)
    address: str = Field(min_length=1, max_length=255)
    location: str | None = Field(default=None, max_length=128)
    provider: str | None = Field(default=None, max_length=128)
    notes: str | None = Field(default=None, max_length=2048)


class ServerCreateIn(ServerBase):
    enabled: bool = True


class ServerUpdateIn(BaseModel):
    model_config = {"str_strip_whitespace": True, "extra": "forbid"}

    name: str | None = Field(default=None, min_length=1, max_length=128)
    address: str | None = Field(default=None, min_length=1, max_length=255)
    location: str | None = Field(default=None, max_length=128)
    provider: str | None = Field(default=None, max_length=128)
    notes: str | None = Field(default=None, max_length=512)
    enabled: bool | None = None


class ServerOut(ORMModel):
    id: uuid.UUID
    name: str
    address: str
    location: str | None = None
    provider: str | None = None
    status: str
    enabled: bool
    cpu_percent: float | None = None
    memory_percent: float | None = None
    disk_percent: float | None = None
    network_rx_bps: int | None = None
    network_tx_bps: int | None = None
    uptime_seconds: int | None = None
    notes: str | None = None
    service_count: int = 0
    created_at: datetime
    updated_at: datetime


class SystemMetricsOut(BaseModel):
    """Local host metrics — sampled read-only, no shell exposure."""

    cpu_percent: float
    memory_percent: float
    memory_total_bytes: int
    memory_used_bytes: int
    disk_percent: float
    disk_total_bytes: int
    disk_used_bytes: int
    network_rx_bps: int
    network_tx_bps: int
    uptime_seconds: int
    load_average: list[float] | None = None
    timestamp: datetime
    extra: dict[str, Any] | None = None
