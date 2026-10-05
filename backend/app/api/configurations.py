"""Configuration management endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import client_ip, require_permission
from app.core.logging import get_logger
from app.models import Service, ServiceConfig, User
from app.schemas.common import MessageOut, Paginated, PaginationParams, validate_sort_field
from app.schemas.config import (
    ConfigCreateIn,
    ConfigDuplicateIn,
    ConfigGeneratedOut,
    ConfigGenerateIn,
    ConfigListItem,
    ConfigOut,
    ConfigUpdateIn,
)
from app.schemas.transports import SecurityType
from app.services import audit_service
from app.services.config_generator import (
    ConfigGenerationError,
    generate_config,
    generate_uuid,
    qr_code_data_url,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/configurations", tags=["configurations"])

# Columns a caller is allowed to sort by. Anything else is rejected so a
# request can never drive an arbitrary ORDER BY expression.
CONFIG_SORTABLE = {"created_at", "name", "protocol", "enabled"}


def _row_to_out(row: ServiceConfig) -> ConfigOut:
    return ConfigOut(
        id=row.id,
        name=row.name,
        uuid=row.uuid,
        protocol=row.protocol,
        transport=row.transport,
        service_id=row.service_id,
        host=row.host,
        port=row.port,
        path=row.path,
        sni=row.sni,
        host_header=row.host_header,
        flow=row.flow,
        security=row.security,
        tls_server_name=row.tls_server_name,
        fingerprint=row.fingerprint,
        alpn=row.alpn,
        allow_insecure=row.allow_insecure,
        extra=row.extra,
        metadata=row.metadata,
        enabled=row.enabled,
        expires_at=row.expires_at,
        last_used_at=row.last_used_at,
        notes=row.notes,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _share_url_for(row: ServiceConfig) -> str:
    from app.schemas.config import ConfigBase
    from app.schemas.transports import ProtocolType, TransportType

    try:
        base = ConfigBase(
            name=row.name,
            protocol=ProtocolType(row.protocol),
            transport=TransportType(row.transport),
            host=row.host,
            port=row.port,
            path=row.path,
            host_header=row.host_header,
            sni=row.sni,
            flow=row.flow,
        )
        params = base.transport_params()
        from app.services.config_generator import build_share_url

        return build_share_url(
            ProtocolType(row.protocol), row.uuid, params, row.name
        )
    except Exception:  # noqa: BLE001 — never break a listing on one bad row
        return ""


def _row_to_list_item(row: ServiceConfig) -> ConfigListItem:
    return ConfigListItem(
        id=row.id,
        name=row.name,
        uuid=row.uuid,
        protocol=row.protocol,
        transport=row.transport,
        host=row.host,
        share_url=_share_url_for(row),
        enabled=row.enabled,
        expires_at=row.expires_at,
        created_at=row.created_at,
        service_id=row.service_id,
    )


async def _load_config(db: AsyncSession, config_id: uuid.UUID) -> ServiceConfig:
    row = await db.get(ServiceConfig, config_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Configuration not found")
    return row


@router.get("", response_model=Paginated[ConfigListItem])
@router.get("/", response_model=Paginated[ConfigListItem], include_in_schema=False)
async def list_configs(
    db: AsyncSession = Depends(get_db),
    params: PaginationParams = Depends(),
    service_id: uuid.UUID | None = None,
    protocol: str | None = None,
    transport: str | None = None,
    enabled: bool | None = None,
    _user: User=Depends(require_permission("config:view")),
) -> Paginated[ConfigListItem]:
    conditions = []
    if service_id is not None:
        conditions.append(ServiceConfig.service_id == service_id)
    if protocol:
        conditions.append(ServiceConfig.protocol == protocol)
    if transport:
        conditions.append(ServiceConfig.transport == transport)
    if enabled is not None:
        conditions.append(ServiceConfig.enabled == enabled)
    if params.search:
        conditions.append(ServiceConfig.name.ilike(f"%{params.search}%"))

    total = await db.scalar(
        select(func.count()).select_from(ServiceConfig).where(*conditions)
    )
    validate_sort_field(params.sort_by, CONFIG_SORTABLE)
    order_col = ServiceConfig.created_at
    if params.sort_by == "name":
        order_col = ServiceConfig.name  # type: ignore[assignment]
    elif params.sort_by == "protocol":
        order_col = ServiceConfig.protocol  # type: ignore[assignment]
    elif params.sort_by == "enabled":
        order_col = ServiceConfig.enabled  # type: ignore[assignment]
    order = order_col.desc() if params.sort_order == "desc" else order_col.asc()

    stmt = (
        select(ServiceConfig)
        .where(*conditions)
        .order_by(order, ServiceConfig.id.desc())
        .offset(params.offset)
        .limit(params.page_size)
    )
    rows = (await db.execute(stmt)).scalars().unique().all()
    return Paginated.build(
        items=[_row_to_list_item(r) for r in rows],
        total=int(total or 0),
        page=params.page,
        page_size=params.page_size,
    )


@router.post("", response_model=ConfigOut, status_code=status.HTTP_201_CREATED)
async def create_config(
    request: Request,
    payload: ConfigCreateIn,
    db: AsyncSession = Depends(get_db),
    user: User=Depends(require_permission("config:create")),
) -> ConfigOut:
    try:
        generated = generate_config(payload)
    except ConfigGenerationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    if payload.service_id is not None:
        service = await db.get(Service, payload.service_id)
        if service is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")

    row = ServiceConfig(
        name=payload.name,
        uuid=generated.client_uuid,
        protocol=payload.protocol.value,
        transport=payload.transport.value,
        service_id=payload.service_id,
        host=payload.host,
        port=payload.port,
        path=payload.path,
        sni=payload.sni or payload.tls_server_name,
        host_header=payload.host_header,
        flow=payload.flow,
        security=payload.security.value,
        tls_server_name=payload.tls_server_name,
        fingerprint=payload.fingerprint,
        alpn=payload.alpn,
        allow_insecure=payload.allow_insecure,
        extra=payload.extra,
        metadata=payload.metadata,
        notes=payload.notes,
        expires_at=payload.expires_at,
    )
    db.add(row)
    await db.flush()
    await audit_service.log_action(
        db,
        action="config.create",
        resource_type="config",
        resource_id=str(row.id),
        details={"name": row.name, "protocol": row.protocol, "transport": row.transport},
        actor=user,
        ip_address=client_ip(request),
    )
    await db.commit()
    return _row_to_out(row)


@router.post("/generate", response_model=ConfigGeneratedOut)
async def generate(
    request: Request,
    payload: ConfigGenerateIn,
    db: AsyncSession = Depends(get_db),
    user: User=Depends(require_permission("config:generate")),
) -> ConfigGeneratedOut:
    """Run the validation → transport → protocol → output pipeline."""
    if payload.config is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A full config payload is required",
        )

    try:
        generated = generate_config(payload.config)
    except ConfigGenerationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    from app.services.config_generator import build_xray_inbound

    inbound = build_xray_inbound(
        generated, tag=payload.config.name, email=payload.config.name
    )

    row = ServiceConfig(
        name=payload.config.name,
        uuid=generated.client_uuid,
        protocol=payload.config.protocol.value,
        transport=payload.config.transport.value,
        service_id=payload.config.service_id,
        host=payload.config.host,
        port=payload.config.port,
        path=payload.config.path,
        sni=payload.config.sni or payload.config.tls_server_name,
        host_header=payload.config.host_header,
        flow=payload.config.flow,
        security=payload.config.security.value,
        tls_server_name=payload.config.tls_server_name,
        fingerprint=payload.config.fingerprint,
        alpn=payload.config.alpn,
        allow_insecure=payload.config.allow_insecure,
        extra=payload.config.extra,
        metadata=payload.config.metadata,
        notes=payload.config.notes,
        expires_at=payload.config.expires_at,
    )
    db.add(row)
    await db.flush()

    await audit_service.log_action(
        db,
        action="config.generate",
        resource_type="config",
        resource_id=str(row.id),
        details={
            "name": row.name,
            "protocol": row.protocol,
            "transport": row.transport,
        },
        actor=user,
        ip_address=client_ip(request),
    )
    await db.commit()

    return ConfigGeneratedOut(
        config=_row_to_out(row),
        share_url=generated.share_url,
        xray=inbound,
        qr_code=qr_code_data_url(generated.share_url),
    )


@router.get("/{config_id}", response_model=ConfigOut)
async def get_config(
    config_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User=Depends(require_permission("config:view")),
) -> ConfigOut:
    return _row_to_out(await _load_config(db, config_id))


@router.patch("/{config_id}", response_model=ConfigOut)
async def update_config(
    request: Request,
    config_id: uuid.UUID,
    payload: ConfigUpdateIn,
    db: AsyncSession = Depends(get_db),
    user: User=Depends(require_permission("config:update")),
) -> ConfigOut:
    row = await _load_config(db, config_id)
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(row, key, value)
    await db.flush()

    # Re-validate the full record through the transport model after a change.
    try:
        base = _row_to_out(row)
        _revalidate(row)
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    await audit_service.log_action(
        db,
        action="config.update",
        resource_type="config",
        resource_id=str(row.id),
        details=data,
        actor=user,
        ip_address=client_ip(request),
    )
    await db.commit()
    del base
    return _row_to_out(row)


def _revalidate(row: ServiceConfig) -> None:
    """Re-run transport validation against the stored record."""
    from app.schemas.config import ConfigBase
    from app.schemas.transports import ProtocolType, TransportType

    ConfigBase(
        name=row.name,
        protocol=ProtocolType(row.protocol),
        transport=TransportType(row.transport),
        host=row.host,
        port=row.port,
        path=row.path,
        host_header=row.host_header,
        sni=row.sni,
        flow=row.flow,
        security=SecurityType(row.security),
        fingerprint=row.fingerprint,
        alpn=row.alpn,
        allow_insecure=row.allow_insecure,
        extra=row.extra,
    ).transport_params()


@router.delete("/{config_id}", response_model=MessageOut)
async def delete_config(
    request: Request,
    config_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User=Depends(require_permission("config:delete")),
) -> MessageOut:
    row = await _load_config(db, config_id)
    name = row.name
    await db.delete(row)
    await audit_service.log_action(
        db,
        action="config.delete",
        resource_type="config",
        resource_id=str(config_id),
        details={"name": name},
        actor=user,
        ip_address=client_ip(request),
    )
    await db.commit()
    return MessageOut(message="Configuration deleted")


@router.post(
    "/{config_id}/duplicate",
    response_model=ConfigOut,
    status_code=status.HTTP_201_CREATED,
)
async def duplicate_config(
    request: Request,
    config_id: uuid.UUID,
    payload: ConfigDuplicateIn | None = None,
    db: AsyncSession = Depends(get_db),
    user: User=Depends(require_permission("config:create")),
) -> ConfigOut:
    source = await _load_config(db, config_id)
    new_name = (payload.name if payload and payload.name else f"{source.name} (copy)")

    row = ServiceConfig(
        name=new_name,
        uuid=generate_uuid(),
        protocol=source.protocol,
        transport=source.transport,
        service_id=source.service_id,
        host=source.host,
        port=source.port,
        path=source.path,
        sni=source.sni,
        host_header=source.host_header,
        flow=source.flow,
        security=source.security,
        tls_server_name=source.tls_server_name,
        fingerprint=source.fingerprint,
        alpn=source.alpn,
        allow_insecure=source.allow_insecure,
        extra=dict(source.extra) if source.extra else None,
        metadata=dict(source.metadata) if source.metadata else None,
        notes=source.notes,
        expires_at=source.expires_at,
    )
    db.add(row)
    await db.flush()
    await audit_service.log_action(
        db,
        action="config.duplicate",
        resource_type="config",
        resource_id=str(row.id),
        details={"source": str(source.id), "name": new_name},
        actor=user,
        ip_address=client_ip(request),
    )
    await db.commit()
    return _row_to_out(row)


@router.post("/{config_id}/enable", response_model=ConfigOut)
@router.post("/{config_id}/disable", response_model=ConfigOut)
async def toggle_config(
    request: Request,
    config_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User=Depends(require_permission("config:update")),
) -> ConfigOut:
    # The value is derived from the route path, never from the request body.
    enabled = request.url.path.endswith("/enable")
    row = await _load_config(db, config_id)
    row.enabled = enabled
    await db.flush()
    await audit_service.log_action(
        db,
        action="config.enable" if enabled else "config.disable",
        resource_type="config",
        resource_id=str(row.id),
        actor=user,
        ip_address=client_ip(request),
    )
    await db.commit()
    return _row_to_out(row)


@router.get("/{config_id}/export")
async def export_config(
    config_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission("config:view")),
) -> JSONResponse:
    """Export a configuration as a downloadable JSON file."""

    row = await _load_config(db, config_id)
    payload = {
        "name": row.name,
        "uuid": row.uuid,
        "protocol": row.protocol,
        "transport": row.transport,
        "host": row.host,
        "port": row.port,
        "path": row.path,
        "sni": row.sni,
        "host_header": row.host_header,
        "flow": row.flow,
        "security": row.security,
        "fingerprint": row.fingerprint,
        "alpn": row.alpn,
        "allow_insecure": row.allow_insecure,
        "extra": row.extra,
        "metadata": row.metadata,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        "share_url": _share_url_for(row),
    }
    safe_name = "".join(c if c.isalnum() or c in "-_." else "_" for c in row.name)
    return JSONResponse(
        content=payload,
        headers={"Content-Disposition": f'attachment; filename="zynox-{safe_name}.json"'},
    )
