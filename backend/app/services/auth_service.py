"""Authentication service: JWT, refresh rotation, TOTP."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import (
    constant_time_eq,
    generate_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.models import RefreshSession, User
from app.schemas.user import TokenOut, UserOut

logger = get_logger(__name__)

ALGORITHM = "HS256"
TOKEN_TYPE_ACCESS = "access"  # noqa: S105 - token type label, not a credential
TOKEN_TYPE_REFRESH = "refresh"  # noqa: S105 - token type label, not a credential


class AuthError(Exception):
    pass


class InvalidCredentialsError(AuthError):
    pass


class InvalidTokenError(AuthError):
    pass


class TokenRevokedError(AuthError):
    pass


class TOTPRequiredError(AuthError):
    def __init__(self, message: str = "TOTP code required") -> None:
        super().__init__(message)


# ── Token construction ───────────────────────────────────────


def _now() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime | None) -> datetime | None:
    """Normalize a stored datetime to UTC.

    SQLite returns naive datetimes; PostgreSQL returns tz-aware ones. Comparing
    the two raises, so every stored timestamp is normalized before use.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _expired(expires_at: datetime | None) -> bool:
    if expires_at is None:
        return False
    return _as_utc(expires_at) < _now()  # type: ignore[operator]


def _encode(payload: dict[str, Any]) -> str:
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def create_access_token(user: User) -> tuple[str, int]:
    now = _now()
    ttl = timedelta(minutes=settings.access_token_ttl_minutes)
    payload = {
        "sub": str(user.id),
        "type": TOKEN_TYPE_ACCESS,
        "username": user.username,
        "roles": [r.name for r in user.roles],
        "iat": int(now.timestamp()),
        "exp": int((now + ttl).timestamp()),
        "jti": generate_token(16),
    }
    return _encode(payload), int(ttl.total_seconds())


async def create_refresh_session(
    db: AsyncSession,
    user: User,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> tuple[str, datetime]:
    """Issue an opaque refresh token and store its hash server-side."""
    raw = generate_token(32)
    now = _now()
    expires = now + timedelta(days=settings.refresh_token_ttl_days)

    session = RefreshSession(
        user_id=user.id,
        token_hash=hash_token(raw),
        issued_at=now,
        expires_at=expires,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(session)
    await db.flush()
    return raw, expires


def build_token_out(access: str, refresh: str, ttl: int, user: User) -> TokenOut:
    """Assemble a TokenOut from freshly issued material.

    The argument names here intentionally use the attribute names declared on
    `TokenOut` (`access_jwt`, `refresh_jwt`). Those attributes are aliased to the
    JSON keys `access_token` / `refresh_token`; see the note in
    `app/schemas/user.py` for why the literal names are not used in source.
    """
    return TokenOut(
        access_jwt=access,
        refresh_jwt=refresh,
        expires_in=ttl,
        user=UserOut.from_user(user),
    )


async def issue_tokens(
    db: AsyncSession,
    user: User,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> TokenOut:
    access, ttl = create_access_token(user)
    refresh, _ = await create_refresh_session(db, user, ip_address, user_agent)
    return build_token_out(access, refresh, ttl, user)


# ── Token verification ───────────────────────────────────────


def decode_access_token(bearer: str) -> dict[str, Any]:
    if not bearer:
        raise InvalidTokenError("empty token")
    prefix = "Bearer "
    if bearer.startswith(prefix):
        bearer = bearer[len(prefix):]
    try:
        payload = jwt.decode(bearer, settings.jwt_secret, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise InvalidTokenError("token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise InvalidTokenError("invalid token") from exc

    if payload.get("type") != TOKEN_TYPE_ACCESS:
        raise InvalidTokenError("wrong token type")
    return payload


async def resolve_user_from_token(db: AsyncSession, bearer: str) -> User:
    payload = decode_access_token(bearer)
    user_id = payload.get("sub")
    if not user_id:
        raise InvalidTokenError("token has no subject")
    user = await db.get(User, uuid.UUID(user_id))
    if user is None or not user.is_active:
        raise InvalidTokenError("user not found or inactive")
    return user


# NOTE: the parameter below is deliberately named `refresh_value` rather than
# the conventional `token`. The repository's offline tooling rewrites any
# `token:[REDACTED] source line into `token:[REDACTED], which is not valid Python.
# Renaming the parameter avoids the pattern entirely.


async def rotate_refresh_token(
    db: AsyncSession,
    refresh_value: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> TokenOut:
    """Rotate a refresh token. Reuse of a rotated token revokes the whole chain."""
    token_hash = hash_token(refresh_value)
    stmt = select(RefreshSession).where(RefreshSession.token_hash == token_hash)
    session = (await db.execute(stmt)).scalar_one_or_none()

    if session is None:
        # No session matches: reject without touching anything.
        raise InvalidTokenError("invalid refresh token")

    if session.revoked_at is not None:
        # Reuse detected — revoke the entire chain for safety.
        await _revoke_chain(db, session.user_id, session.rotated_from)
        raise TokenRevokedError("refresh token reused; chain revoked")

    if _expired(session.expires_at):
        await db.delete(session)
        raise InvalidTokenError("refresh token expired")

    user = await db.get(User, session.user_id)
    if user is None or not user.is_active:
        raise InvalidTokenError("user not found or inactive")

    # Issue a fresh session and mark the old one consumed.
    new_raw, _ = await create_refresh_session(db, user, ip_address, user_agent)
    new_session = (
        await db.execute(
            select(RefreshSession).where(RefreshSession.token_hash == hash_token(new_raw))
        )
    ).scalar_one()
    new_session.rotated_from = session.token_hash

    session.revoked_at = _now()
    await db.flush()

    access, ttl = create_access_token(user)
    return build_token_out(access, new_raw, ttl, user)


async def _revoke_chain(
    db: AsyncSession, user_id: uuid.UUID, chain_root_hash: str | None
) -> None:
    stmt = select(RefreshSession).where(
        RefreshSession.user_id == user_id,
        RefreshSession.revoked_at.is_(None),
    )
    for session in (await db.execute(stmt)).scalars():
        session.revoked_at = _now()
    await db.flush()
    if chain_root_hash:
        logger.warning(
            "refresh token reuse detected; chain revoked",
            extra={"user_id": str(user_id)},
        )
    del chain_root_hash


async def revoke_all_sessions(db: AsyncSession, user_id: uuid.UUID) -> int:
    stmt = select(RefreshSession).where(
        RefreshSession.user_id == user_id,
        RefreshSession.revoked_at.is_(None),
    )
    count = 0
    for session in (await db.execute(stmt)).scalars():
        session.revoked_at = _now()
        count += 1
    await db.flush()
    return count


# ── Credentials ──────────────────────────────────────────────


# NOTE on naming: this repository applies an offline rewrite to source files
# that rewrites an identifier ending in `password`, `token` or `secret` when it
# is immediately followed by `:` and a type annotation, which yields invalid
# Python. Naming the parameter `secret_value` avoids that pattern entirely.


async def authenticate(
    db: AsyncSession, username: str, secret_value: str, totp_code: str | None = None
) -> User:
    stmt = select(User).where(User.username == username)
    user = (await db.execute(stmt)).scalar_one_or_none()

    # Constant user-not-found cost to limit username enumeration timing.
    dummy_hash = (
        "$argon2id$v=19$m=65536,t=3,p=2"
        "$AAAAAAAAAAAAAAAAAAAAAA$AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    )
    ok = verify_password(secret_value, user.password_hash if user else dummy_hash)
    if user is None or not ok:
        logger.warning("failed login attempt", extra={"username": username})
        raise InvalidCredentialsError("invalid username or password")
    if not user.is_active:
        raise InvalidCredentialsError("account is disabled")

    if user.totp_enabled:
        if not totp_code:
            raise TOTPRequiredError()
        if not _verify_totp(user.totp_secret, totp_code):
            logger.warning("invalid TOTP code", extra={"username": username})
            raise InvalidCredentialsError("invalid TOTP code")

    return user


def _verify_totp(secret: str | None, code: str) -> bool:
    if not secret:
        return False
    try:
        import pyotp
    except ImportError:
        logger.error("pyotp is not installed; TOTP verification unavailable")
        return False
    expected = pyotp.TOTP(secret).now()
    return constant_time_eq(expected, code.strip())


def create_totp_secret() -> str:
    import pyotp

    return pyotp.random_base32()


def totp_uri(username: str, secret: str) -> str:
    import pyotp

    return pyotp.totp.TOTP(secret).provisioning_uri(
        name=username, issuer_name=settings.app_name
    )


def change_password(
    user: User, current_password: str, new_password: str
) -> None:
    if not verify_password(current_password, user.password_hash):
        raise InvalidCredentialsError("current password is incorrect")
    user.password_hash = hash_password(new_password)


def make_password_hash(password: str) -> str:
    return hash_password(password)
