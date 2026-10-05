"""FastAPI authentication and authorization dependencies.

RBAC is enforced here so that no router can forget to protect an endpoint.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logging import get_logger
from app.models import User
from app.services.auth_service import (
    InvalidCredentialsError,
    InvalidTokenError,
    TokenRevokedError,
    resolve_user_from_token,
)

logger = get_logger(__name__)

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> User:
    """Resolve the user from the Authorization: Bearer header."""
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user = await resolve_user_from_token(db, credentials.credentials)
    except (InvalidTokenError, TokenRevokedError, ValueError) as exc:
        logger.info("rejected token", extra={"reason": str(exc)})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except InvalidCredentialsError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    request.state.user = user
    return user


async def get_current_user_optional(
    db: AsyncSession = Depends(get_db),
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> User | None:
    """Like get_current_user but returns None instead of raising 401."""
    if credentials is None or not credentials.credentials:
        return None
    try:
        return await resolve_user_from_token(db, credentials.credentials)
    except Exception:  # noqa: BLE001 — optional auth must never 500
        return None


def require_permission(permission: str) -> Callable[..., Any]:
    """Dependency factory: require the given permission on the route."""

    async def dependency(user: User = Depends(get_current_user)) -> User:
        if user.has_permission(permission):
            return user
        logger.info(
            "permission denied",
            extra={"user": user.username, "permission": permission},
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Missing permission: {permission}",
        )

    return dependency


def require_admin() -> Callable[..., Any]:
    return require_permission("setting:update")


def require_any_role(*roles: str) -> Callable[..., Any]:
    async def dependency(user: User = Depends(get_current_user)) -> User:
        if any(user.has_role(r) for r in roles):
            return user
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role"
        )

    return dependency


def client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


async def require_telegram_authorization(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    """Authenticate a Telegram Mini App request via server-side initData check.

    Never trusts client-side initDataUnsafe.
    """
    from app.services.telegram_service import TelegramAuthService

    init_data = await _extract_init_data(request)
    if not init_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Telegram initData",
        )

    service = TelegramAuthService(db)
    try:
        user = await service.authenticate_web_app(init_data)
    except Exception as exc:  # noqa: BLE001
        logger.info("telegram webapp auth failed", extra={"reason": str(exc)})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Telegram authentication failed",
        ) from exc

    request.state.user = user
    return user


async def _extract_init_data(request: Request) -> str | None:
    """Read initData from the Authorization header or JSON body (never query)."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[len("Bearer "):].strip() or None
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001 — body may be absent or non-JSON
        return None
    if isinstance(body, dict):
        value = body.get("init_data") or body.get("initData")
        if isinstance(value, str):
            return value
    return None
