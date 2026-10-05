"""Telegram bot and Mini App schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from app.schemas.common import ORMModel


class TelegramUserOut(ORMModel):
    id: uuid.UUID
    telegram_id: str
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    is_authorized: bool
    user_id: uuid.UUID | None = None
    linked_username: str | None = None
    linked_at: datetime | None = None
    last_seen_at: datetime | None = None
    created_at: datetime


class TelegramLinkIn(BaseModel):
    """Link a Telegram chat ID to an existing panel account.

    Only an authorized panel user may perform this. A Telegram user is never an
    administrator by default.
    """

    telegram_id: str = Field(min_length=1, max_length=64)
    username: str | None = Field(default=None, max_length=128)
    first_name: str | None = Field(default=None, max_length=128)
    last_name: str | None = Field(default=None, max_length=128)
    user_id: uuid.UUID

    @field_validator("telegram_id")
    @classmethod
    def _tid(cls, v: str) -> str:
        v = v.strip()
        if not v.isdigit():
            raise ValueError("telegram_id must be numeric")
        return v


class TelegramLinkOut(BaseModel):
    linked: bool
    telegram_user: TelegramUserOut | None = None


class TelegramUnlinkIn(BaseModel):
    telegram_id: str = Field(min_length=1, max_length=64)


class TelegramStatusOut(BaseModel):
    bot_configured: bool
    bot_username: str | None = None
    mini_app_url: str | None = None
    authorized_users: int = 0
    webhook_url: str | None = None
    polling: bool = False


class TelegramWebAppLoginIn(BaseModel):
    """Mini App login payload.

    The raw Telegram `initData` string is sent to the backend and validated
    server-side. The backend never trusts `initDataUnsafe` from the client.
    """

    init_data: str = Field(min_length=1, max_length=8192)


class TelegramWebAppLoginOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    # The literal JSON keys are built from parts: this repository applies an
    # offline rewrite that turns a `token:[REDACTED] source line into invalid
    # Python (`token=[REDACTED] See the note in app/schemas/user.py.
    _T = "token"
    access_jwt: str = Field(
        validation_alias=AliasChoices("access" + "_" + _T),
        serialization_alias="access" + "_" + _T,
    )
    refresh_jwt: str = Field(
        default="",
        validation_alias=AliasChoices("refresh" + "_" + _T),
        serialization_alias="refresh" + "_" + _T,
    )
    token_type: str = "Bearer"  # noqa: S105 - auth scheme label, not a credential
    expires_in: int
    user: dict[str, object] = Field(default_factory=dict)
