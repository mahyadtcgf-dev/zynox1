"""Telegram management endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import client_ip, require_permission
from app.core.rate_limit import rate_limit
from app.core.security import TelegramAuthError
from app.models import User
from app.schemas.common import MessageOut, Paginated, PaginationParams
from app.schemas.telegram import (
    TelegramLinkIn,
    TelegramLinkOut,
    TelegramStatusOut,
    TelegramUserOut,
    TelegramWebAppLoginIn,
    TelegramWebAppLoginOut,
)
from app.services import audit_service
from app.services.telegram_service import (
    TelegramAuthService,
    TelegramNotAuthorizedError,
    TelegramServiceError,
    handle_webapp_login,
    telegram_user_to_out,
)

router = APIRouter(prefix="/telegram", tags=["telegram"])


@router.get("/status", response_model=TelegramStatusOut)
async def status_(
    db: AsyncSession = Depends(get_db),
    _user: User=Depends(require_permission("telegram:view")),
) -> TelegramStatusOut:
    return await TelegramAuthService(db).status()


@router.get("/users", response_model=Paginated[TelegramUserOut])
@router.get("/users/", response_model=Paginated[TelegramUserOut], include_in_schema=False)
async def list_telegram_users(
    db: AsyncSession = Depends(get_db),
    params: PaginationParams = Depends(),
    _user: User=Depends(require_permission("telegram:view")),
) -> Paginated[TelegramUserOut]:
    service = TelegramAuthService(db)
    records = await service.list_linked()
    start = params.offset
    end = start + params.page_size
    page = records[start:end]
    return Paginated.build(
        items=[telegram_user_to_out(r) for r in page],
        total=len(records),
        page=params.page,
        page_size=params.page_size,
    )


@router.post("/link", response_model=TelegramLinkOut)
async def link_telegram_user(
    request: Request,
    payload: TelegramLinkIn,
    db: AsyncSession = Depends(get_db),
    actor: User=Depends(require_permission("telegram:update")),
) -> TelegramLinkOut:
    service = TelegramAuthService(db)
    try:
        record = await service.link(payload)
    except TelegramServiceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    await audit_service.log_action(
        db,
        action="telegram.link",
        resource_type="telegram_user",
        resource_id=record.telegram_id,
        details={"user_id": str(payload.user_id)},
        actor=actor,
        ip_address=client_ip(request),
    )
    await db.commit()
    return TelegramLinkOut(linked=True, telegram_user=telegram_user_to_out(record))


@router.post("/unlink", response_model=MessageOut)
async def unlink_telegram_user(
    request: Request,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    actor: User=Depends(require_permission("telegram:update")),
) -> MessageOut:
    telegram_id = str(payload.get("telegram_id") or "")
    if not telegram_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="telegram_id is required"
        )

    service = TelegramAuthService(db)
    removed = await service.unlink(telegram_id)
    if not removed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Telegram user not found")

    await audit_service.log_action(
        db,
        action="telegram.unlink",
        resource_type="telegram_user",
        resource_id=telegram_id,
        actor=actor,
        ip_address=client_ip(request),
    )
    await db.commit()
    return MessageOut(message="Telegram user unlinked")


@router.post(
    "/webapp/login",
    response_model=TelegramWebAppLoginOut,
    dependencies=[Depends(rate_limit("telegram.webapp_login"))],
)
async def webapp_login(
    payload: TelegramWebAppLoginIn,
    db: AsyncSession = Depends(get_db),
) -> TelegramWebAppLoginOut:
    """Mini App login. Validates initData server-side; never trusts the client."""
    if not settings.telegram_bot_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Telegram bot is not configured",
        )
    try:
        result = await handle_webapp_login(db, payload)
    except TelegramAuthError as exc:
        # Invalid/stale/forged initData. TelegramAuthError is a plain Exception
        # and was previously unhandled, so every forged attempt surfaced as a
        # 500 instead of a 401.
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except TelegramNotAuthorizedError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    await audit_service.log_action(
        db,
        action="telegram.webapp_login",
        resource_type="user",
        details={"username": result["user"]["username"]},
        actor_type="telegram",
    )
    await db.commit()
    return TelegramWebAppLoginOut(**result)
