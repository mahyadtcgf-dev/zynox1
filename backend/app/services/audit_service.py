"""Audit logging service."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import scrub
from app.models import AuditLog
from app.schemas.common import Paginated, PaginationParams
from app.schemas.settings import AuditLogOut


async def log_action(
    db: AsyncSession,
    *,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    details: dict[str, Any] | None = None,
    actor: Any = None,
    actor_type: str = "user",
    status: str = "success",
    ip_address: str | None = None,
    user_agent: str | None = None,
    commit: bool = False,
) -> AuditLog:
    """Record a privileged action. Details are scrubbed of secrets."""
    entry = AuditLog(
        actor_id=getattr(actor, "id", None) if actor else None,
        actor_username=getattr(actor, "username", None) if actor else None,
        actor_type=actor_type,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id is not None else None,
        details=scrub(details) if details is not None else None,
        status=status,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(entry)
    if commit:
        await db.commit()
    else:
        await db.flush()
    return entry


async def list_audit_logs(
    db: AsyncSession,
    params: PaginationParams,
    *,
    action: str | None = None,
    resource_type: str | None = None,
    actor_username: str | None = None,
    log_status: str | None = None,
) -> Paginated[AuditLogOut]:
    """Paginated, filterable audit log read-out."""
    conditions = []
    if action:
        conditions.append(AuditLog.action == action)
    if resource_type:
        conditions.append(AuditLog.resource_type == resource_type)
    if actor_username:
        conditions.append(AuditLog.actor_username == actor_username)
    if log_status:
        conditions.append(AuditLog.status == log_status)
    if params.search:
        conditions.append(AuditLog.action.ilike(f"%{params.search}%"))

    from sqlalchemy import func

    count_stmt = select(func.count()).select_from(AuditLog)
    if conditions:
        count_stmt = count_stmt.where(*conditions)
    total = (await db.execute(count_stmt)).scalar_one()

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
        .order_by(order, AuditLog.id.desc())
        .offset(params.offset)
        .limit(params.page_size)
    )
    if conditions:
        stmt = stmt.where(*conditions)

    rows = (await db.execute(stmt)).scalars().unique().all()
    return Paginated.build(
        items=[AuditLogOut.model_validate(r) for r in rows],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )
