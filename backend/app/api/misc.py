"""Settings, audit log, dashboard, server, and health endpoints."""

from __future__ import annotations

import uuid
from datetime import UTC
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import require_permission
from app.models import AuditLog, Server, Service, ServiceConfig, SystemSetting, TelegramUser, User
from app.schemas.common import Paginated, PaginationParams, validate_sort_field
from app.schemas.service import ServerCreateIn, ServerOut, ServerUpdateIn, SystemMetricsOut
from app.schemas.settings import (
    AUDIT_SORTABLE,
    AuditLogOut,
    DashboardStatsOut,
    SystemMetricsSummary,
    SystemSettingOut,
    SystemSettingUpdateIn,
)
from app.services.monitoring_service import sample_metrics, to_summary

# ── Settings ─────────────────────────────────────────────────

settings_router = APIRouter(prefix="/settings", tags=["settings"])


@settings_router.get("", response_model=list[SystemSettingOut])
@settings_router.get("/", response_model=list[SystemSettingOut], include_in_schema=False)
async def list_settings(
    db: AsyncSession = Depends(get_db),
    _user: User=Depends(require_permission("setting:view")),
) -> list[SystemSettingOut]:
    rows = (await db.execute(select(SystemSetting).order_by(SystemSetting.key))).scalars().all()
    return [SystemSettingOut.model_validate(r) for r in rows]


@settings_router.put("", response_model=SystemSettingOut)
async def upsert_setting(
    payload: SystemSettingUpdateIn,
    db: AsyncSession = Depends(get_db),
    actor: User=Depends(require_permission("setting:update")),
) -> SystemSettingOut:
    row = (
        await db.execute(select(SystemSetting).where(SystemSetting.key == payload.key))
    ).scalar_one_or_none()
    if row is None:
        row = SystemSetting(key=payload.key)
        db.add(row)
    row.value = payload.value
    if payload.description is not None:
        row.description = payload.description
    await db.commit()
    await db.refresh(row)
    return SystemSettingOut.model_validate(row)


# ── Audit logs ───────────────────────────────────────────────

logs_router = APIRouter(prefix="/logs", tags=["logs"])


@logs_router.get("/audit", response_model=Paginated[AuditLogOut])
@logs_router.get("/audit/", response_model=Paginated[AuditLogOut], include_in_schema=False)
async def list_audit_logs(
    db: AsyncSession = Depends(get_db),
    params: PaginationParams = Depends(),
    action: str | None = None,
    resource_type: str | None = None,
    actor_username: str | None = None,
    status_: str | None = None,
    _user: User=Depends(require_permission("log:view")),
) -> Paginated[AuditLogOut]:
    # Whitelist the sort column so a caller can never inject an arbitrary
    # expression into ORDER BY.
    validate_sort_field(params.sort_by, AUDIT_SORTABLE)

    conditions = []
    if action:
        conditions.append(AuditLog.action == action)
    if resource_type:
        conditions.append(AuditLog.resource_type == resource_type)
    if actor_username:
        conditions.append(AuditLog.actor_username == actor_username)
    if status_:
        conditions.append(AuditLog.status == status_)
    if params.search:
        conditions.append(AuditLog.action.ilike(f"%{params.search}%"))

    total = await db.scalar(select(func.count()).select_from(AuditLog).where(*conditions))
    order_col = AuditLog.created_at
    if params.sort_by == "action":
        order_col = AuditLog.action  # type: ignore[assignment]
    elif params.sort_by == "resource_type":
        order_col = AuditLog.resource_type  # type: ignore[assignment]
    elif params.sort_by == "actor_username":
        order_col = AuditLog.actor_username  # type: ignore[assignment]
    elif params.sort_by == "status":
        order_col = AuditLog.status  # type: ignore[assignment]
    order = order_col.desc() if params.sort_order == "desc" else order_col.asc()

    stmt = (
        select(AuditLog)
        .where(*conditions)
        .order_by(order, AuditLog.id.desc())
        .offset(params.offset)
        .limit(params.page_size)
    )
    rows = (await db.execute(stmt)).scalars().unique().all()
    return Paginated.build(
        items=[AuditLogOut.model_validate(r) for r in rows],
        total=int(total or 0),
        page=params.page,
        page_size=params.page_size,
    )


# ── Dashboard ────────────────────────────────────────────────

dashboard_router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@dashboard_router.get("/stats", response_model=DashboardStatsOut)
async def dashboard_stats(
    db: AsyncSession = Depends(get_db),
    _user: User=Depends(require_permission("service:view")),
) -> DashboardStatsOut:
    async def _count(model: type[Any], *filters: Any) -> int:
        stmt = select(func.count()).select_from(model)
        if filters:
            stmt = stmt.where(*filters)
        return int((await db.scalar(stmt)) or 0)

    services_total = await _count(Service)
    services_active = await _count(Service, Service.enabled.is_(True), Service.status == "running")
    services_offline = await _count(Service, Service.status == "stopped")
    services_disabled = await _count(Service, Service.enabled.is_(False))

    configs_total = await _count(ServiceConfig)
    configs_active = await _count(ServiceConfig, ServiceConfig.enabled.is_(True))
    from datetime import datetime

    now = datetime.now(UTC)
    configs_expired = await _count(
        ServiceConfig, ServiceConfig.expires_at.is_not(None), ServiceConfig.expires_at < now
    )

    users_total = await _count(User)
    users_active = await _count(User, User.is_active.is_(True))

    servers_total = await _count(Server)
    servers_online = await _count(Server, Server.status == "online")

    tg_authorized = await _count(TelegramUser, TelegramUser.is_authorized.is_(True))

    metrics = sample_metrics()

    recent_rows = (
        await db.execute(
            select(AuditLog).order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(8)
        )
    ).scalars().unique().all()

    return DashboardStatsOut(
        app_name=settings.app_name,
        services_total=services_total,
        services_active=services_active,
        services_offline=services_offline,
        services_disabled=services_disabled,
        configs_total=configs_total,
        configs_active=configs_active,
        configs_expired=configs_expired,
        users_total=users_total,
        users_active=users_active,
        servers_total=servers_total,
        servers_online=servers_online,
        telegram_bot_configured=bool(settings.telegram_bot_token),
        telegram_authorized_users=tg_authorized,
        system=SystemMetricsSummary(**to_summary(metrics)),
        recent_activity=[AuditLogOut.model_validate(r) for r in recent_rows],
    )


# ── Servers ──────────────────────────────────────────────────

servers_router = APIRouter(prefix="/servers", tags=["servers"])


@servers_router.get("", response_model=Paginated[ServerOut])
@servers_router.get("/", response_model=Paginated[ServerOut], include_in_schema=False)
async def list_servers(
    db: AsyncSession = Depends(get_db),
    params: PaginationParams = Depends(),
    _user: User=Depends(require_permission("server:view")),
) -> Paginated[ServerOut]:
    conditions = []
    if params.search:
        conditions.append(Server.name.ilike(f"%{params.search}%"))

    total = await db.scalar(select(func.count()).select_from(Server).where(*conditions))
    stmt = (
        select(Server)
        .where(*conditions)
        .order_by(Server.created_at.desc(), Server.id.desc())
        .offset(params.offset)
        .limit(params.page_size)
    )
    rows = (await db.execute(stmt)).scalars().unique().all()
    return Paginated.build(
        items=[ServerOut.model_validate(r) for r in rows],
        total=int(total or 0),
        page=params.page,
        page_size=params.page_size,
    )


@servers_router.post("", response_model=ServerOut, status_code=status.HTTP_201_CREATED)
async def create_server(
    payload: ServerCreateIn,
    db: AsyncSession = Depends(get_db),
    actor: User=Depends(require_permission("setting:update")),
) -> ServerOut:
    server = Server(**payload.model_dump())
    db.add(server)
    await db.commit()
    await db.refresh(server)
    return ServerOut.model_validate(server)


@servers_router.patch("/{server_id}", response_model=ServerOut)
async def update_server(
    server_id: uuid.UUID,
    payload: ServerUpdateIn,
    db: AsyncSession = Depends(get_db),
    actor: User=Depends(require_permission("setting:update")),
) -> ServerOut:
    server = await db.get(Server, server_id)
    if server is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Server not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(server, key, value)
    await db.commit()
    await db.refresh(server)
    return ServerOut.model_validate(server)


@servers_router.delete("/{server_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_server(
    server_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: User=Depends(require_permission("setting:update")),
) -> None:
    server = await db.get(Server, server_id)
    if server is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Server not found")
    await db.delete(server)
    await db.commit()


# ── System metrics ───────────────────────────────────────────

metrics_router = APIRouter(prefix="/system", tags=["system"])


@metrics_router.get("/metrics", response_model=SystemMetricsOut)
async def system_metrics(
    _user: User=Depends(require_permission("server:view")),
) -> SystemMetricsOut:
    return sample_metrics()
