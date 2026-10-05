"""Base repository with pagination and safe sorting."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any, Generic, TypeVar

from pydantic import BaseModel
from sqlalchemy import asc, desc, func, inspect, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from app.models.base import Base
from app.schemas.common import Paginated, PaginationParams

T = TypeVar("T", bound=Base)

_SAFE_COLUMN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class BaseRepository(Generic[T]):
    """Generic async repository with whitelist-protected sorting."""

    model: type[T]

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── Helpers ───────────────────────────────────────────────
    def _column(self, name: str) -> Any:
        """Resolve a column by name, whitelist-matched against the mapper."""
        if not _SAFE_COLUMN_RE.match(name):
            raise ValueError(f"invalid column name: {name!r}")
        mapper = inspect(self.model)
        column = mapper.columns.get(name)
        if column is None:
            raise ValueError(f"unknown column: {name!r}")
        return column

    def _apply_order(
        self, stmt: Select, params: PaginationParams, default: str = "created_at"
    ) -> Select:
        sort_by = params.sort_by or default
        try:
            column = self._column(sort_by)
        except ValueError:
            column = self._column(default)
        return stmt.order_by(
            desc(column) if params.sort_order == "desc" else asc(column)
        )

    async def _paginate(
        self, stmt: Select, params: PaginationParams, conditions: Sequence[Any] = ()
    ) -> Paginated[Any]:
        where: list[Any] = list(conditions)
        if where:
            stmt = stmt.where(*where)
        total = await self.db.scalar(
            select(func.count()).select_from(stmt.order_by(None).limit(None))  # type: ignore[arg-type]
        )
        stmt = self._apply_order(stmt, params)
        stmt = stmt.offset(params.offset).limit(params.page_size)
        rows = (await self.db.execute(stmt)).scalars().unique().all()
        return Paginated.build(  # type: ignore[arg-type]
            items=list(rows), total=int(total or 0), page=params.page, page_size=params.page_size
        )

    # ── CRUD ──────────────────────────────────────────────────
    async def get_by_id(self, id_: Any) -> T | None:
        return await self.db.get(self.model, id_)

    async def list(self, params: PaginationParams) -> Paginated[T]:
        return await self._paginate(select(self.model), params)  # type: ignore[return-value]

    async def add(self, instance: T, commit: bool = False) -> T:
        self.db.add(instance)
        await self.db.flush()
        if commit:
            await self.db.commit()
        return instance

    async def delete(self, instance: T, commit: bool = False) -> None:
        await self.db.delete(instance)
        if commit:
            await self.db.commit()
        else:
            await self.db.flush()


class SchemaRepository(BaseRepository[T]):
    """Repository that maps rows to Pydantic schemas."""

    schema: type[BaseModel]

    async def to_schema(self, instance: T) -> BaseModel:
        return self.schema.model_validate(instance)
