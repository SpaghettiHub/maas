#  Copyright 2024 Canonical Ltd.  This software is licensed under the
#  GNU Affero General Public License version 3 (see the file LICENSE).

from typing import List

from maasservicelayer.context import Context
from maasservicelayer.db.filters import QuerySpec
from maasservicelayer.db.repositories.zones import ZonesRepository
from maasservicelayer.exceptions.catalog import (
    BadRequestException,
    BaseExceptionDetail,
)
from maasservicelayer.exceptions.constants import (
    CANNOT_DELETE_DEFAULT_ZONE_VIOLATION_TYPE,
)
from maasservicelayer.models.zones import Zone
from maasservicelayer.services._base import BaseService
from maasservicelayer.services.nodes import NodesService
from maasservicelayer.services.vmcluster import VmClustersService


class ZonesService(BaseService[Zone, ZonesRepository]):
    def __init__(
        self,
        context: Context,
        nodes_service: NodesService,
        vmcluster_service: VmClustersService,
        zones_repository: ZonesRepository,
    ):
        super().__init__(context, zones_repository)
        self.nodes_service = nodes_service
        self.vmcluster_service = vmcluster_service

    async def delete_many(self, query: QuerySpec) -> List[Zone]:
        """
        Delete zones matching a query. All the resources in the zone will be moved to the default zone.
        """
        zones = await self.get_many(query)
        deleted_zones = []
        for zone in zones:
            deleted_zone = await self._delete(zone)
            deleted_zones.append(deleted_zone)
        return deleted_zones

    async def delete_by_id(
        self, zone_id: int, etag_if_match: str | None = None
    ) -> Zone | None:
        """
        Delete a zone. All the resources in the zone will be moved to the default zone.
        """
        zone = await self.get_by_id(zone_id)
        return await self._delete(zone, etag_if_match)

    async def delete_one(
        self, query: QuerySpec, etag_if_match: str | None = None
    ) -> Zone | None:
        """
        Delete a zone. All the resources in the zone will be moved to the default zone.
        """
        zone = await self.get_one(query)
        return await self._delete(zone, etag_if_match)

    async def _delete(
        self, zone: Zone | None, etag_if_match: str | None = None
    ) -> Zone | None:
        if not zone:
            return None

        self.etag_check(zone, etag_if_match)
        default_zone = await self.repository.get_default_zone()

        if default_zone.id == zone.id:
            raise BadRequestException(
                details=[
                    BaseExceptionDetail(
                        type=CANNOT_DELETE_DEFAULT_ZONE_VIOLATION_TYPE,
                        message="The default zone can not be deleted.",
                    )
                ]
            )
        deleted_resource = await self.repository.delete_by_id(id=zone.id)

        # Cascade deletion to the related models and move the resources from the deleted zone to the default zone
        await self.nodes_service.move_to_zone(zone.id, default_zone.id)
        await self.nodes_service.move_bmcs_to_zone(zone.id, default_zone.id)
        await self.vmcluster_service.move_to_zone(zone.id, default_zone.id)

        return deleted_resource
