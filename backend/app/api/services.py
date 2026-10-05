"""Service management endpoints."""

from __future__ import annotations

import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import client_ip, require_permission
from app.core.logging import get_logger
from app.integrations.xray.adapter import XrayAdapter, XrayError, XrayNotAvailableError
from app.models import Service, ServiceConfig, User
from app.schemas.common import MessageOut, Paginated, PaginationParams, validate_sort_field
from app.schemas.service import (
    ServiceActionIn,
    ServiceActionOut,
    ServiceCreateIn,
    ServiceLogOut,
    ServiceOut,
    ServiceUpdateIn,
)
from app.services import audit_service

logger = get_logger(__name__)

router = APIRouter(prefix="/services", tags=["services"])

SERVICE_SORTABLE = {"created_at", "name", "status"}


async def _to_out(db: AsyncSession, service: Service) -> ServiceOut:
    return ServiceOut(
        id=service.id,
        name=service.name,
        description=service.description,
        host=service.host,
        port=service.port,
        protocol=service.protocol,
        transport=service.transport,
        tag=service.tag,
        status=service.status,
        enabled=service.enabled,
        server_id=service.server_id,  # type: ignore[arg-type]
        last_error=service.last_error,
        config_count=0,
        created_at=service.created_at,
        updated_at=service.updated_at,
    )


async def _load_service(db: AsyncSession, service_id: uuid.UUID) -> Service:
    service = await db.get(Service, service_id)
    if service is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")
    return service


@router.get("", response_model=Paginated[ServiceOut])
@router.get("/", response_model=Paginated[ServiceOut], include_in_schema=False)
async def list_services(
    db: AsyncSession = Depends(get_db),
    params: PaginationParams = Depends(),
    _user: User=Depends(require_permission("service:view")),
) -> Paginated[ServiceOut]:
    from sqlalchemy import func, select

    conditions = []
    if params.search:
        conditions.append(Service.name.ilike(f"%{params.search}%"))

    total = await db.scalar(
        select(func.count()).select_from(Service).where(*conditions)
    )
    validate_sort_field(params.sort_by, SERVICE_SORTABLE)
    order_col = Service.created_at
    if params.sort_by == "name":
        order_col = Service.name  # type: ignore[assignment]
    elif params.sort_by == "status":
        order_col = Service.status  # type: ignore[assignment]
    order = order_col.desc() if params.sort_order == "desc" else order_col.asc()

    stmt = (
        select(Service)
        .where(*conditions)
        .order_by(order, Service.id.desc())
        .offset(params.offset)
        .limit(params.page_size)
    )
    rows = (await db.execute(stmt)).scalars().unique().all()

    # Batch config counts to avoid an N+1 query.
    ids = [r.id for r in rows]
    counts: dict[uuid.UUID, int] = {}
    if ids:
        count_rows = (
            await db.execute(
                select(ServiceConfig.service_id, func.count())
                .where(ServiceConfig.service_id.in_(ids))
                .group_by(ServiceConfig.service_id)
            )
        ).all()
        counts = {row[0]: row[1] for row in count_rows}  # type: ignore[misc]

    items = []
    for row in rows:
        out = await _to_out(db, row)
        out.config_count = counts.get(row.id, 0)
        items.append(out)

    return Paginated.build(
        items=items, total=int(total or 0), page=params.page, page_size=params.page_size
    )


@router.post("", response_model=ServiceOut, status_code=status.HTTP_201_CREATED)
async def create_service(
    request: Request,
    payload: ServiceCreateIn,
    db: AsyncSession = Depends(get_db),
    user: User=Depends(require_permission("service:create")),
) -> ServiceOut:
    service = Service(**payload.model_dump())
    service.status = "unknown"
    db.add(service)
    await db.flush()
    await audit_service.log_action(
        db,
        action="service.create",
        resource_type="service",
        resource_id=str(service.id),
        details={
            "name": service.name,
            "protocol": service.protocol,
            "transport": service.transport,
        },
        actor=user,
        ip_address=client_ip(request),
    )
    await db.commit()
    return await _to_out(db, service)


@router.get("/{service_id}", response_model=ServiceOut)
async def get_service(
    service_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User=Depends(require_permission("service:view")),
) -> ServiceOut:
    service = await _load_service(db, service_id)
    return await _to_out(db, service)


@router.patch("/{service_id}", response_model=ServiceOut)
async def update_service(
    request: Request,
    service_id: uuid.UUID,
    payload: ServiceUpdateIn,
    db: AsyncSession = Depends(get_db),
    user: User=Depends(require_permission("service:update")),
) -> ServiceOut:
    service = await _load_service(db, service_id)
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(service, key, value)
    await db.flush()
    await audit_service.log_action(
        db,
        action="service.update",
        resource_type="service",
        resource_id=str(service.id),
        details=data,
        actor=user,
        ip_address=client_ip(request),
    )
    await db.commit()
    return await _to_out(db, service)


@router.delete("/{service_id}", response_model=MessageOut)
async def delete_service(
    request: Request,
    service_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User=Depends(require_permission("service:delete")),
) -> MessageOut:
    service = await _load_service(db, service_id)
    name = service.name
    await db.delete(service)
    await audit_service.log_action(
        db,
        action="service.delete",
        resource_type="service",
        resource_id=str(service_id),
        details={"name": name},
        actor=user,
        ip_address=client_ip(request),
    )
    await db.commit()
    return MessageOut(message="Service deleted")


@router.post("/{service_id}/action", response_model=ServiceActionOut)
async def service_action(
    request: Request,
    service_id: uuid.UUID,
    payload: ServiceActionIn,
    db: AsyncSession = Depends(get_db),
    user: User=Depends(require_permission("service:control")),
) -> ServiceActionOut:
    """Predefined safe service action. Never accepts a free-form command."""
    service = await _load_service(db, service_id)
    adapter = XrayAdapter()
    started = time.perf_counter()
    message = ""
    new_status = service.status

    try:
        if payload.action == "test":
            result = await adapter.test_connectivity(service.host, service.port)
            message = result["message"]
            new_status = "running" if result["reachable"] else "stopped"
        elif payload.action == "start":
            status_ = await adapter.start()
            message = "started" if status_.running else "failed to start"
            new_status = "running" if status_.running else "stopped"
        elif payload.action == "stop":
            await adapter.stop()
            message = "stopped"
            new_status = "stopped"
        elif payload.action == "restart":
            status_ = await adapter.restart()
            message = "restarted" if status_.running else "failed to restart"
            new_status = "running" if status_.running else "stopped"
        elif payload.action == "reload":
            await adapter.reload()
            message = "reload signalled"
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported action"
            )
    except XrayNotAvailableError as exc:
        message = "xray is not available on this host"
        new_status = "unknown"
        logger.info("xray unavailable", extra={"error": str(exc)})
    except XrayError as exc:
        message = str(exc)
        new_status = "degraded"

    service.status = new_status
    await db.flush()
    await audit_service.log_action(
        db,
        action=f"service.{payload.action}",
        resource_type="service",
        resource_id=str(service.id),
        details={"message": message},
        actor=user,
        ip_address=client_ip(request),
    )
    await db.commit()
    return ServiceActionOut(
        action=payload.action,
        status=new_status,
        message=message,
        duration_ms=int((time.perf_counter() - started) * 1000),
    )


@router.get("/{service_id}/logs", response_model=list[ServiceLogOut])
async def service_logs(
    service_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User=Depends(require_permission("service:view")),
) -> list[ServiceLogOut]:
    service = await _load_service(db, service_id)
    del service
    return []
