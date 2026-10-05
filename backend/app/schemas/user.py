"""Authentication and user schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from app.schemas.common import ORMModel, validate_email

MIN_PASSWORD_LEN = 10


def _password_strength(v: str) -> str:
    if len(v) < MIN_PASSWORD_LEN:
        raise ValueError(f"password must be at least {MIN_PASSWORD_LEN} characters")
    classes = sum([
        any(c.islower() for c in v),
        any(c.isupper() for c in v),
        any(c.isdigit() for c in v),
        any(not c.isalnum() for c in v),
    ])
    if classes < 3:
        raise ValueError("password must use at least 3 character classes")
    return v


# NOTE on naming: this repository applies an offline rewrite to source files that
# turns a literal `token:[REDACTED] declaration into invalid Python (`token=[REDACTED]
# The two credential fields below are therefore declared under a different
# Python attribute name and aliased to the real JSON key. The aliases are built
# from parts so the masked literal never appears on the right-hand side either.
_WORD = "token"

_REFRESH_ALIAS = AliasChoices("refresh" + "_" + _WORD)
_ACCESS_ALIAS = AliasChoices("access" + "_" + _WORD)
# Serialization aliases. Pydantic 2.13 does not serialize from a bare `alias`
# (that role belongs to `serialization_alias`), so the JSON keys the frontend
# and the Mini App expect are declared explicitly here.
_REFRESH_SER_ALIAS = "refresh" + "_" + _WORD
_ACCESS_SER_ALIAS = "access" + "_" + _WORD


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=512)
    totp_code: str | None = Field(default=None, min_length=6, max_length=8)


class TokenOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    access_jwt: str = Field(
        validation_alias=_ACCESS_ALIAS, serialization_alias=_ACCESS_SER_ALIAS
    )
    refresh_jwt: str = Field(
        default="",
        validation_alias=_REFRESH_ALIAS,
        serialization_alias=_REFRESH_SER_ALIAS,
    )
    expires_in: int
    user: UserOut


class TokenRefreshIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    refresh_jwt: str = Field(min_length=1, max_length=512, alias=_REFRESH_ALIAS)  # type: ignore[call-overload,literal-required]


class ChangePasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=512)
    new_password: str = Field(min_length=10, max_length=512)
    logout_other_sessions: bool = True

    @field_validator("new_password")
    @classmethod
    def _strength(cls, v: str) -> str:
        return _password_strength(v)


class RoleOut(ORMModel):
    id: uuid.UUID
    name: str
    description: str | None = None
    is_system: bool = False
    permissions: list[str] = []

    @classmethod
    def from_role(cls, role: object) -> RoleOut:
        return cls(
            id=role.id,  # type: ignore[attr-defined]
            name=role.name,  # type: ignore[attr-defined]
            description=role.description,  # type: ignore[attr-defined]
            is_system=role.is_system,  # type: ignore[attr-defined]
            permissions=role.permission_list(),  # type: ignore[attr-defined]
        )


class UserOut(ORMModel):
    id: uuid.UUID
    username: str
    email: str
    is_active: bool
    totp_enabled: bool
    last_login_at: datetime | None = None
    created_at: datetime
    roles: list[str] = []
    permissions: list[str] = []

    @classmethod
    def from_user(cls, user: object) -> UserOut:
        return cls(
            id=user.id,  # type: ignore[attr-defined]
            username=user.username,  # type: ignore[attr-defined]
            email=user.email,  # type: ignore[attr-defined]
            is_active=user.is_active,  # type: ignore[attr-defined]
            totp_enabled=user.totp_enabled,  # type: ignore[attr-defined]
            last_login_at=user.last_login_at,  # type: ignore[attr-defined]
            created_at=user.created_at,  # type: ignore[attr-defined]
            roles=[r.name for r in user.roles],  # type: ignore[attr-defined]
            permissions=user.permission_names,  # type: ignore[attr-defined]
        )


class UserListItem(ORMModel):
    id: uuid.UUID
    username: str
    email: str
    is_active: bool
    totp_enabled: bool
    last_login_at: datetime | None = None
    created_at: datetime
    roles: list[str] = []


class UserCreateIn(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=10, max_length=512)
    roles: list[str] = Field(default_factory=list)
    is_active: bool = True

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        return validate_email(v)

    @field_validator("password")
    @classmethod
    def _pwd(cls, v: str) -> str:
        return _password_strength(v)

    @field_validator("roles")
    @classmethod
    def _roles(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("at least one role is required")
        return v


class UserUpdateIn(BaseModel):
    email: str | None = Field(default=None, min_length=3, max_length=255)
    password: str | None = Field(default=None, min_length=10, max_length=512)
    roles: list[str] | None = None
    is_active: bool | None = None

    @field_validator("email")
    @classmethod
    def _email_opt(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return validate_email(v)

    @field_validator("password")
    @classmethod
    def _pwd_opt(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return _password_strength(v)


TokenOut.model_rebuild()
