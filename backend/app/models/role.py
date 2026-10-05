"""RBAC: roles and permissions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Column, ForeignKey, String, Table, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from app.models import User


from app.models.base import Base, TimestampMixin, UUIDPrimaryKey

# ── Permission catalogue ─────────────────────────────────────
# Central definition so the seeder and the authorization layer agree exactly.

PERMISSIONS: tuple[tuple[str, str], ...] = (
    # Services
    ("service:view", "View services"),
    ("service:create", "Create services"),
    ("service:update", "Update services"),
    ("service:delete", "Delete services"),
    ("service:control", "Start/stop/restart services"),
    # Configurations
    ("config:view", "View configurations"),
    ("config:create", "Create configurations"),
    ("config:update", "Update configurations"),
    ("config:delete", "Delete configurations"),
    ("config:generate", "Generate configurations"),
    # Users
    ("user:view", "View users"),
    ("user:create", "Create users"),
    ("user:update", "Update users"),
    ("user:delete", "Delete users"),
    # Servers
    ("server:view", "View servers and metrics"),
    # Telegram
    ("telegram:view", "View Telegram settings"),
    ("telegram:update", "Update Telegram settings"),
    # Logs
    ("log:view", "View audit logs"),
    # Settings
    ("setting:view", "View system settings"),
    ("setting:update", "Update system settings"),
)

ROLE_PERMISSIONS: dict[str, tuple[str, ...]] = {
    "admin": tuple(p for p, _ in PERMISSIONS),
    "operator": (
        "service:view", "service:create", "service:update", "service:control",
        "config:view", "config:create", "config:update", "config:generate",
        "user:view",
        "server:view",
        "telegram:view",
        "log:view",
        "setting:view",
    ),
    "viewer": (
        "service:view",
        "config:view",
        "user:view",
        "server:view",
        "telegram:view",
        "log:view",
        "setting:view",
    ),
}


class Role(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "roles"

    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_system: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default=text("false")
    )
    permissions: Mapped[list[str] | None] = mapped_column(
        String(4096), nullable=True
    )

    users: Mapped[list[User]] = relationship(  # noqa: F821  # type: ignore[name-defined]
        "User",
        secondary="user_roles",
        back_populates="roles",
    )

    def permission_list(self) -> list[str]:
        if not self.permissions:
            return []
        return [p for p in self.permissions.split(",") if p]  # type: ignore[attr-defined]


class Permission(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "permissions"

    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)


# ── Association tables ───────────────────────────────────────

user_roles = Table(
    "user_roles",
    Base.metadata,
    Column(
        "user_id", PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True,
    ),
    Column(
        "role_id", PG_UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True, index=True,
    ),
)

role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column(
        "role_id", PG_UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True, index=True,
    ),
    Column(
        "permission_id", PG_UUID(as_uuid=True),
        ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True, index=True,
    ),
)


class UserRole(Base):
    """Explicit association model (used by Alembic introspection + queries)."""

    __table__ = user_roles


class RolePermission(Base):
    __table__ = role_permissions
