"""Service configuration repository."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ServiceConfig
from app.repositories.base import BaseRepository
from app.schemas.common import Paginated, PaginationParams


class ConfigRepository(BaseRepository[ServiceConfig]):
    model = ServiceConfig

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db)

    async def list_configs(
        self,
        params: PaginationParams,
        *,
        service_id: uuid.UUID | None = None,
        protocol: str | None = None,
        transport: str | None = None,
        enabled: bool | None = None,
    ) -> Paginated[ServiceConfig]:
        conditions = []
        if service_id is not None:
            conditions.append(ServiceConfig.service_id == service_id)
        if protocol:
            conditions.append(ServiceConfig.protocol == protocol)
        if transport:
            conditions.append(ServiceConfig.transport == transport)
        if enabled is not None:
            conditions.append(ServiceConfig.enabled == enabled)
        if params.search:
            conditions.append(ServiceConfig.name.ilike(f"%{params.search}%"))

        return await self._paginate(select(self.model), params, conditions)

    async def get_by_uuid(self, client_uuid: str) -> ServiceConfig | None:
        stmt = select(ServiceConfig).where(ServiceConfig.uuid == client_uuid)
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def name_exists(self, name: str, exclude_id: uuid.UUID | None = None) -> bool:
        stmt = select(ServiceConfig.id).where(ServiceConfig.name == name)
        if exclude_id is not None:
            stmt = stmt.where(ServiceConfig.id != exclude_id)
        return (await self.db.execute(stmt)).first() is not None

    async def count_active(self) -> int:
        stmt = select(ServiceConfig).where(ServiceConfig.enabled.is_(True))
        return len((await self.db.execute(stmt)).scalars().all())

    async def count_total(self) -> int:
        stmt = select(ServiceConfig)
        return len((await self.db.execute(stmt)).scalars().all())
