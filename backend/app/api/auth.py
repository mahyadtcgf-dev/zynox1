"""Authentication endpoints."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import client_ip, get_current_user
from app.core.logging import get_logger
from app.core.rate_limit import rate_limit
from app.models import User
from app.schemas.common import MessageOut
from app.schemas.user import (
    ChangePasswordIn,
    LoginIn,
    TokenOut,
    TokenRefreshIn,
    UserOut,
)
from app.services import audit_service
from app.services.auth_service import (
    authenticate,
    change_password,
    issue_tokens,
    revoke_all_sessions,
    rotate_refresh_token,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/login",
    response_model=TokenOut,
    dependencies=[Depends(rate_limit("auth.login"))],
)
async def login(
    request: Request,
    payload: LoginIn,
    db: AsyncSession = Depends(get_db),
) -> TokenOut:
    user = await authenticate(db, payload.username, payload.password, payload.totp_code)
    user.last_login_at = datetime.now(UTC)
    user.last_login_ip = client_ip(request)
    await db.flush()

    tokens = await issue_tokens(
        db, user, ip_address=client_ip(request), user_agent=request.headers.get("user-agent")
    )
    await audit_service.log_action(
        db,
        action="auth.login",
        resource_type="user",
        resource_id=str(user.id),
        actor=user,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    await db.commit()
    return tokens


@router.post(
    "/refresh",
    response_model=TokenOut,
    dependencies=[Depends(rate_limit("auth.refresh"))],
)
async def refresh(
    request: Request,
    payload: TokenRefreshIn,
    db: AsyncSession = Depends(get_db),
) -> TokenOut:
    tokens = await rotate_refresh_token(
        db,
        payload.refresh_jwt,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    await db.commit()
    return tokens


@router.post("/logout", response_model=MessageOut, status_code=status.HTTP_200_OK)
async def logout(
    request: Request,
    payload: TokenRefreshIn,
    db: AsyncSession = Depends(get_db),
) -> MessageOut:
    from sqlalchemy import select

    from app.core.security import hash_token
    from app.models import RefreshSession

    session = (
        await db.execute(
            select(RefreshSession).where(
                RefreshSession.token_hash == hash_token(payload.refresh_jwt)
            )
        )
    ).scalar_one_or_none()
    if session is not None:
        await db.delete(session)
    await audit_service.log_action(
        db,
        actor=None,
        action="auth.logout",
        resource_type="user",
        ip_address=client_ip(request),
    )
    await db.commit()
    return MessageOut(message="Logged out")


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.from_user(user)


@router.post("/change-password", response_model=MessageOut,
             dependencies=[Depends(rate_limit("auth.change_password"))])
async def change_my_password(
    request: Request,
    payload: ChangePasswordIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageOut:
    change_password(user, payload.current_password, payload.new_password)
    if payload.logout_other_sessions:
        await revoke_all_sessions(db, user.id)
    await audit_service.log_action(
        db,
        action="auth.change_password",
        resource_type="user",
        resource_id=str(user.id),
        actor=user,
        ip_address=client_ip(request),
    )
    await db.commit()
    return MessageOut(message="Password changed")
