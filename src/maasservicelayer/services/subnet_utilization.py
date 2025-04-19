# Copyright 2025 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from maascommon.utils.network import MAASIPSet
from maasservicelayer.context import Context
from maasservicelayer.db.repositories.subnet_utilization import (
    SubnetUtilizationRepository,
)
from maasservicelayer.exceptions.catalog import (
    BaseExceptionDetail,
    NotFoundException,
)
from maasservicelayer.exceptions.constants import (
    UNEXISTING_RESOURCE_VIOLATION_TYPE,
)
from maasservicelayer.models.subnets import Subnet
from maasservicelayer.services.base import Service
from maasservicelayer.services.subnets import SubnetsService


class V3SubnetUtilizationService(Service):
    def __init__(
        self,
        context: Context,
        subnets_service: SubnetsService,
        subnet_utilization_repository: SubnetUtilizationRepository,
    ) -> None:
        super().__init__(context)
        self.repository = subnet_utilization_repository
        self.subnets_service = subnets_service

    async def _get_subnet_or_raise_exception(self, subnet_id: int) -> Subnet:
        subnet = await self.subnets_service.get_by_id(id=subnet_id)
        if subnet is None:
            raise NotFoundException(
                details=[
                    BaseExceptionDetail(
                        type=UNEXISTING_RESOURCE_VIOLATION_TYPE,
                        message=f"Could not find subnet with id {subnet_id}.",
                    )
                ]
            )
        return subnet

    async def get_ipranges_available_for_reserved_range(
        self, subnet_id: int, exclude_ip_range_id: int | None = None
    ) -> MAASIPSet:
        subnet = await self._get_subnet_or_raise_exception(subnet_id)
        return await self.repository.get_ipranges_available_for_reserved_range(
            subnet=subnet, exclude_ip_range_id=exclude_ip_range_id
        )

    async def get_ipranges_available_for_dynamic_range(
        self, subnet_id: int, exclude_ip_range_id: int | None = None
    ) -> MAASIPSet:
        subnet = await self._get_subnet_or_raise_exception(subnet_id)
        return await self.repository.get_ipranges_available_for_dynamic_range(
            subnet=subnet, exclude_ip_range_id=exclude_ip_range_id
        )

    async def get_ipranges_for_ip_allocation(
        self,
        subnet_id: int,
        exclude_addresses: list[str] | None = None,
    ) -> MAASIPSet:
        subnet = await self._get_subnet_or_raise_exception(subnet_id)
        return await self.repository.get_ipranges_for_ip_allocation(
            subnet=subnet,
            exclude_addresses=exclude_addresses,
        )

    async def get_free_ipranges(
        self,
        subnet_id: int,
    ) -> MAASIPSet:
        subnet = await self._get_subnet_or_raise_exception(subnet_id)
        return await self.repository.get_free_ipranges(subnet=subnet)

    async def get_subnet_utilization(
        self,
        subnet_id: int,
    ) -> MAASIPSet:
        subnet = await self._get_subnet_or_raise_exception(subnet_id)
        return await self.repository.get_subnet_utilization(subnet=subnet)

    async def get_ipranges_in_use(
        self,
        subnet_id: int,
    ) -> MAASIPSet:
        subnet = await self._get_subnet_or_raise_exception(subnet_id)
        return await self.repository.get_ipranges_in_use(subnet=subnet)
