"""Panel users."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from app.models import Role


from app.models.base import Base, TimestampMixin, UUIDPrimaryKey


class User(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Optional TOTP 2FA (RFC 6238).
    totp_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_login_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    roles: Mapped[list[Role]] = relationship(  # noqa: F821  # type: ignore[name-defined]
        "Role",
        secondary="user_roles",
        back_populates="users",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_users_username", "username"),
        Index("ix_users_email", "email"),
    )

    def has_role(self, name: str) -> bool:
        return any(r.name == name for r in self.roles)

    def has_permission(self, permission: str) -> bool:
        return any(role.permissions and permission in role.permissions for role in self.roles)

    @property
    def is_admin(self) -> bool:
        return self.has_role("admin")

    @property
    def permission_names(self) -> list[str]:
        seen: set[str] = set()
        for role in self.roles:
            if role.permissions:
                seen.update(role.permissions)
        return sorted(seen)


class UserTOTPBackup(UUIDPrimaryKey, Base):
    """Single-use TOTP backup codes, stored hashed."""

    __tablename__ = "user_totp_backups"

    user_id: Mapped[uuid.UUID] = mapped_column(
        nullable=False, index=True
    )
    code_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
