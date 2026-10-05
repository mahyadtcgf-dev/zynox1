"""Settings, audit log, and dashboard schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import ORMModel, validate_sort_field

# ── Settings ─────────────────────────────────────────────────

SETTING_KEYS = {
    "app.name", "app.motd",
    "telegram.mini_app_url",
    "xray.control_mode",
    "xray.binary_path",
    "xray.config_path",
    "xray.api_address",
}


class SystemSettingOut(ORMModel):
    id: uuid.UUID
    key: str
    value: str | None = None
    description: str | None = None
    updated_at: datetime


class SystemSettingUpdateIn(BaseModel):
    model_config = {"extra": "forbid"}

    key: str = Field(min_length=1, max_length=128)
    value: str | None = Field(default=None, max_length=4096)
    description: str | None = Field(default=None, max_length=255)

    @field_validator("key")
    @classmethod
    def _key(cls, v: str) -> str:
        if v not in SETTING_KEYS:
            raise ValueError(f"unknown setting key: {v!r}")
        return v


# ── Audit log ────────────────────────────────────────────────

AUDIT_SORTABLE = {"created_at", "action", "resource_type", "actor_username", "status"}


class AuditLogOut(ORMModel):
    id: uuid.UUID
    actor_id: uuid.UUID | None = None
    actor_username: str | None = None
    actor_type: str
    action: str
    resource_type: str
    resource_id: str | None = None
    details: dict[str, Any] | None = None
    status: str
    ip_address: str | None = None
    user_agent: str | None = None
    created_at: datetime


class AuditLogQuery(BaseModel):
    action: str | None = None
    resource_type: str | None = None
    actor_username: str | None = None
    status: str | None = None
    sort_by: str | None = None

    @field_validator("sort_by")
    @classmethod
    def _sort(cls, v: str | None) -> str | None:
        return validate_sort_field(v, AUDIT_SORTABLE)


# ── Dashboard ───────────────────────────────────────────────

class DashboardStatsOut(BaseModel):
    app_name: str
    services_total: int
    services_active: int
    services_offline: int
    services_disabled: int
    configs_total: int
    configs_active: int
    configs_expired: int
    users_total: int
    users_active: int
    servers_total: int
    servers_online: int
    telegram_bot_configured: bool
    telegram_authorized_users: int
    system: SystemMetricsSummary | None = None
    recent_activity: list[AuditLogOut] = Field(default_factory=list)


class SystemMetricsSummary(BaseModel):
    cpu_percent: float
    memory_percent: float
    disk_percent: float
    network_rx_bps: int
    network_tx_bps: int
    uptime_seconds: int


DashboardStatsOut.model_rebuild()
AuditLogOut.model_rebuild()
