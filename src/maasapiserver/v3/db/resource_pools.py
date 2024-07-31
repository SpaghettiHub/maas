from datetime import datetime
from typing import Any, Optional

from sqlalchemy import desc, insert, select, Select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql.operators import eq, le

from maasapiserver.common.db.sequences import ResourcePoolIdSequence
from maasapiserver.common.db.tables import ResourcePoolTable
from maasapiserver.common.models.constants import (
    UNIQUE_CONSTRAINT_VIOLATION_TYPE,
)
from maasapiserver.common.models.exceptions import (
    AlreadyExistsException,
    BaseExceptionDetail,
)
from maasapiserver.v3.db.base import BaseRepository
from maasapiserver.v3.models.base import ListResult
from maasapiserver.v3.models.resource_pools import ResourcePool

RESOURCE_POOLS_FIELDS = (
    ResourcePoolTable.c.id,
    ResourcePoolTable.c.name,
    ResourcePoolTable.c.description,
    ResourcePoolTable.c.created,
    ResourcePoolTable.c.updated,
)


class ResourcePoolRepository(BaseRepository[ResourcePool]):
    async def get_next_id(self) -> int:
        stmt = select(ResourcePoolIdSequence.next_value())
        return (await self.connection.execute(stmt)).scalar()

    async def find_by_id(self, id: int) -> Optional[ResourcePool]:
        stmt = self._select_all_statement().where(
            eq(ResourcePoolTable.c.id, id)
        )
        if result := await self.connection.execute(stmt):
            if resource_pools := result.one_or_none():
                return ResourcePool(**resource_pools._asdict())
        return None

    async def create(self, resource_pool: ResourcePool) -> ResourcePool:
        stmt = (
            insert(ResourcePoolTable)
            .returning(*RESOURCE_POOLS_FIELDS)
            .values(
                name=resource_pool.name,
                description=resource_pool.description,
                updated=resource_pool.updated,
                created=resource_pool.created,
            )
        )
        try:
            result = await self.connection.execute(stmt)
        except IntegrityError:
            self._raise_constraint_violation(resource_pool.name)
        created_resource_pools = result.one()
        return ResourcePool(**created_resource_pools._asdict())

    async def list(
        self, token: str | None, size: int
    ) -> ListResult[ResourcePool]:
        stmt = (
            self._select_all_statement()
            .order_by(desc(ResourcePoolTable.c.id))
            .limit(size + 1)
        )

        if token is not None:
            stmt = stmt.where(le(ResourcePoolTable.c.id, int(token)))

        result = (await self.connection.execute(stmt)).all()
        next_token = None
        if len(result) > size:
            next_token = result.pop().id
        return ListResult[ResourcePool](
            items=[ResourcePool(**row._asdict()) for row in result],
            next_token=next_token,
        )

    async def delete(self, id: int) -> None:
        raise Exception("Not implemented yet.")

    async def update(self, resource_pool: ResourcePool) -> ResourcePool:
        resource_pool.updated = datetime.utcnow()
        stmt = (
            update(ResourcePoolTable)
            .where(eq(ResourcePoolTable.c.id, resource_pool.id))
            .returning(*RESOURCE_POOLS_FIELDS)
            .values(**resource_pool.dict())
        )
        try:
            new_resource_pool = (await self.connection.execute(stmt)).one()
        except IntegrityError:
            self._raise_constraint_violation(resource_pool.name)
        return ResourcePool(**new_resource_pool._asdict())

    def _select_all_statement(self) -> Select[Any]:
        return select(*RESOURCE_POOLS_FIELDS).select_from(ResourcePoolTable)

    def _raise_constraint_violation(self, name: str):
        raise AlreadyExistsException(
            details=[
                BaseExceptionDetail(
                    type=UNIQUE_CONSTRAINT_VIOLATION_TYPE,
                    message=f"An entity named '{name}' already exists.",
                )
            ]
        )
