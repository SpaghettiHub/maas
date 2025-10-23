#  Copyright 2024-2025 Canonical Ltd.  This software is licensed under the
#  GNU Affero General Public License version 3 (see the file LICENSE).

from maasservicelayer.builders.resource_pools import ResourcePoolBuilder
from maasservicelayer.context import Context
from maasservicelayer.db.filters import QuerySpec
from maasservicelayer.db.repositories.resource_pools import (
    ResourcePoolRepository,
)
from maasservicelayer.exceptions.catalog import (
    BadRequestException,
    BaseExceptionDetail,
)
from maasservicelayer.exceptions.constants import (
    CANNOT_DELETE_DEFAULT_RESOURCEPOOL_VIOLATION_TYPE,
)
from maasservicelayer.models.base import ListResult
from maasservicelayer.models.resource_pools import (
    ResourcePool,
    ResourcePoolWithSummary,
)
from maasservicelayer.services.base import BaseService


class ResourcePoolsService(
    BaseService[ResourcePool, ResourcePoolRepository, ResourcePoolBuilder]
):
    resource_logging_name = "resourcepool"

    def __init__(
        self,
        context: Context,
        resource_pools_repository: ResourcePoolRepository,
    ):
        super().__init__(context, resource_pools_repository)

    async def list_ids(self) -> set[int]:
        """Returns all the ids of the resource pools in the db."""
        return await self.repository.list_ids()

    async def list_with_summary(
        self, page: int, size: int, query: QuerySpec | None
    ) -> ListResult[ResourcePoolWithSummary]:
        return await self.repository.list_with_summary(
            page=page, size=size, query=query
        )

    async def pre_delete_hook(
        self, resource_to_be_deleted: ResourcePool
    ) -> None:
        if resource_to_be_deleted.is_default():
            raise BadRequestException(
                details=[
                    BaseExceptionDetail(
                        type=CANNOT_DELETE_DEFAULT_RESOURCEPOOL_VIOLATION_TYPE,
                        message="The default resource pool cannot be deleted.",
                    )
                ]
            )
