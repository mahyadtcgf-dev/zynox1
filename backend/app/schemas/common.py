"""Shared schema building blocks."""

from __future__ import annotations

import re
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field
from pydantic.config import ConfigDict

T = TypeVar("T")


class ORMModel(BaseModel):
    """Base schema that reads from SQLAlchemy models."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


# ── Pagination ───────────────────────────────────────────────

class Paginated(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int

    @classmethod
    def build(
        cls, items: list[T], total: int, page: int, page_size: int
    ) -> Paginated[T]:
        pages = (total + page_size - 1) // page_size if page_size > 0 else 0
        return cls(items=items, total=total, page=page, page_size=page_size, pages=pages)


class PaginationParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    sort_by: str | None = Field(default=None, max_length=64)
    sort_order: str = Field(default="asc", pattern="^(asc|desc)$")
    search: str | None = Field(default=None, max_length=256)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


# ── Common response envelopes ──────────────────────────────────

class MessageOut(BaseModel):
    message: str
    detail: Any | None = None


class ErrorOut(BaseModel):
    error: str
    detail: Any | None = None
    error_code: str | None = None


# ── Validation helpers ───────────────────────────────────────

_HOST_RE = re.compile(
    r"^(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.[A-Za-z0-9-]{1,63})*$"
)
_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_PATH_RE = re.compile(r"^/[^\s]*$")


def validate_host(v: str) -> str:
    """Hostname or IP literal."""
    if not v:
        raise ValueError("host is required")
    if len(v) > 255:
        raise ValueError("host is too long")
    return v.lower()


def validate_domain(v: str) -> str:
    if not v:
        raise ValueError("domain is required")
    if not _HOST_RE.match(v):
        raise ValueError(f"invalid domain: {v!r}")
    return v.lower()


def validate_path(v: str | None) -> str | None:
    if v is None or v == "":
        return None
    v = v.strip()
    if not v.startswith("/"):
        v = "/" + v
    if not _PATH_RE.match(v):
        raise ValueError(f"invalid path: {v!r}")
    return v


def validate_uuid(v: str) -> str:
    if not v:
        raise ValueError("uuid is required")
    if not _UUID_RE.match(v):
        raise ValueError("invalid UUID format")
    return v.lower()


def validate_email(v: str) -> str:
    if "@" not in v or len(v) > 255:
        raise ValueError("invalid email")
    return v.lower()


def validate_sort_field(v: str | None, allowed: set[str]) -> str | None:
    """Whitelist sort columns to prevent injection through ORDER BY."""
    if v is None:
        return None
    if v not in allowed:
        raise ValueError(f"sorting by {v!r} is not allowed")
    return v
