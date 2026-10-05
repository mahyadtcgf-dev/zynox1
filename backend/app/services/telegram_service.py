"""Telegram bot and Mini App integration.

Security model:
  - Bot token comes from TELEGRAM_BOT_TOKEN (never hardcoded).
  - Telegram users are NEVER administrators by default.
  - Mini App `initData` is validated server-side per the Telegram mechanism.
  - Bot commands enforce the same RBAC as the panel API.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import validate_telegram_init_data
from app.models import TelegramUser, User
from app.schemas.telegram import (
    TelegramLinkIn,
    TelegramStatusOut,
    TelegramUserOut,
    TelegramWebAppLoginIn,
)

logger = get_logger(__name__)

# Alias used for optional text return types. The repository's offline rewrite
# mangles a bare `str` annotation after a colon, so annotations are routed
# through this name.
_OptionalText = "str | None"


class TelegramServiceError(RuntimeError):
    pass


class TelegramNotAuthorizedError(TelegramServiceError):
    pass


class TelegramAuthService:
    """Server-side authentication for the Telegram Mini App."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def authenticate_web_app(self, init_data: str) -> User:
        """Validate initData and return the linked, authorized panel user.

        Raises if the bot token is missing, the signature is invalid, the data
        is stale, or the Telegram account is not linked to an authorized user.
        """
        if not settings.telegram_bot_token:
            raise TelegramNotAuthorizedError("Telegram bot is not configured")

        payload = validate_telegram_init_data(
            init_data, settings.telegram_bot_token
        )
        telegram_id = str(payload["user"]["id"])

        linked = await self._get_linked_user(telegram_id)
        if linked is None:
            raise TelegramNotAuthorizedError(
                "This Telegram account is not linked to a Zynox account"
            )
        if not linked.is_authorized:
            raise TelegramNotAuthorizedError(
                "This Telegram account is not authorized"
            )

        panel_user = linked.user  # type: ignore[attr-defined]
        if panel_user is None or not panel_user.is_active:
            raise TelegramNotAuthorizedError("Linked account is not active")

        linked.last_seen_at = datetime.now(UTC)
        await self.db.flush()
        return panel_user

    async def _get_linked_user(self, telegram_id: str) -> TelegramUser | None:
        stmt = select(TelegramUser).where(TelegramUser.telegram_id == telegram_id)
        return (await self.db.execute(stmt)).scalar_one_or_none()

    # ── Linking (panel-side, requires an authorized panel user) ──
    async def link(self, payload: TelegramLinkIn) -> TelegramUser:
        user = await self.db.get(User, payload.user_id)
        if user is None:
            raise TelegramServiceError("panel user not found")

        existing = await self._get_linked_user(payload.telegram_id)
        record = existing or TelegramUser(telegram_id=payload.telegram_id)
        record.username = payload.username
        record.first_name = payload.first_name
        record.last_name = payload.last_name
        record.user_id = user.id  # type: ignore[assignment]
        record.is_authorized = True
        record.linked_at = datetime.now(UTC)
        record.last_seen_at = datetime.now(UTC)

        self.db.add(record)
        await self.db.flush()
        logger.info(
            "telegram account linked",
            extra={"telegram_id": record.telegram_id, "user": user.username},
        )
        return record

    async def unlink(self, telegram_id: str) -> bool:
        record = await self._get_linked_user(telegram_id)
        if record is None:
            return False
        await self.db.delete(record)
        await self.db.flush()
        return True

    async def list_linked(self) -> list[TelegramUser]:
        stmt = select(TelegramUser).order_by(TelegramUser.created_at.desc())
        return list((await self.db.execute(stmt)).scalars().all())

    async def status(self) -> TelegramStatusOut:
        stmt = select(TelegramUser).where(TelegramUser.is_authorized.is_(True))
        authorized = (await self.db.execute(stmt)).scalars().all()

        # The bot handle is derived from the token, but the token itself is
        # never logged or echoed back to the client.
        bot_username = None
        if settings.telegram_bot_token:
            bot_username = _bot_username_from_token(settings.telegram_bot_token)

        return TelegramStatusOut(
            bot_configured=bool(settings.telegram_bot_token),
            bot_username=bot_username,
            mini_app_url=settings.telegram_mini_app_url or None,
            authorized_users=len(authorized),
        )

    # ── Bot-facing command authorization ─────────────────────
    async def authorize_command(self, telegram_id: str) -> User:
        """Resolve the panel user for a bot command, or raise.

        Used by the Telegram bot. Unlinked accounts receive no administrative
        functionality.
        """
        record = await self._get_linked_user(str(telegram_id))
        if record is None or not record.is_authorized:
            raise TelegramNotAuthorizedError(
                "This Telegram account is not authorized. Ask an administrator "
                "to link your account from the Zynox panel."
            )
        if record.user is None or not record.user.is_active:  # type: ignore[attr-defined]
            raise TelegramNotAuthorizedError("Linked account is not active")
        return record.user  # type: ignore[attr-defined]


def _bot_username_from_token(bot_credential: str | None) -> _OptionalText:  # type: ignore[valid-type]
    """Return a display-only handle derived from the bot credential.

    Only the public bot username is extracted; the credential itself is never
    logged or returned to the client.
    """
    if bot_credential is None:
        return None
    if ":" not in bot_credential:
        return None
    return "@" + bot_credential.split(":", 1)[0]


async def handle_webapp_login(
    db: AsyncSession, payload: TelegramWebAppLoginIn
) -> dict[str, Any]:
    """Mini App login → panel session tokens."""
    service = TelegramAuthService(db)
    user = await service.authenticate_web_app(payload.init_data)
    from app.services.auth_service import issue_tokens

    tokens = await issue_tokens(db, user)
    # Serialize through the model so the JSON keys (`access_token` /
    # `refresh_token`) come from the model's serialization aliases.
    token_payload = tokens.model_dump(by_alias=True, mode="json")
    return {
        "access_token": token_payload["access_token"],
        "refresh_token": token_payload["refresh_token"],
        "token_type": "Bearer",
        "expires_in": tokens.expires_in,
        "user": {
            "id": str(user.id),
            "username": user.username,
            "roles": [r.name for r in user.roles],
        },
    }


def telegram_user_to_out(record: TelegramUser) -> TelegramUserOut:
    linked_username = record.user.username if record.user else None  # type: ignore[attr-defined]
    return TelegramUserOut(
        id=record.id,
        telegram_id=record.telegram_id,
        username=record.username,
        first_name=record.first_name,
        last_name=record.last_name,
        is_authorized=record.is_authorized,
        user_id=record.user_id,  # type: ignore[arg-type]
        linked_username=linked_username,
        linked_at=record.linked_at,
        last_seen_at=record.last_seen_at,
        created_at=record.created_at,
    )
