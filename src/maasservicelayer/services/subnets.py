# Copyright 2024 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).
from pydantic import IPvAnyAddress

from maascommon.workflows.dhcp import (
    CONFIGURE_DHCP_WORKFLOW_NAME,
    ConfigureDHCPParam,
    merge_configure_dhcp_param,
)
from maasservicelayer.context import Context
from maasservicelayer.db.repositories.base import CreateOrUpdateResource
from maasservicelayer.db.repositories.subnets import SubnetsRepository
from maasservicelayer.models.base import ListResult
from maasservicelayer.models.subnets import Subnet
from maasservicelayer.services._base import Service
from maasservicelayer.services.temporal import TemporalService


class SubnetsService(Service):
    def __init__(
        self,
        context: Context,
        temporal_service: TemporalService,
        subnets_repository: SubnetsRepository | None = None,
    ):
        super().__init__(context)
        self.temporal_service = temporal_service
        self.subnets_repository = (
            subnets_repository
            if subnets_repository
            else SubnetsRepository(context)
        )

    async def list(self, token: str | None, size: int) -> ListResult[Subnet]:
        return await self.subnets_repository.list(token=token, size=size)

    async def get_by_id(self, id: int) -> Subnet | None:
        return await self.subnets_repository.find_by_id(id=id)

    async def find_best_subnet_for_ip(
        self, ip: IPvAnyAddress
    ) -> Subnet | None:
        return await self.subnets_repository.find_best_subnet_for_ip(ip)

    async def create(self, resource: CreateOrUpdateResource) -> Subnet:
        subnet = await self.subnets_repository.create(resource)
        self.temporal_service.register_or_update_workflow_call(
            CONFIGURE_DHCP_WORKFLOW_NAME,
            ConfigureDHCPParam(subnet_ids=[subnet.id]),
            parameter_merge_func=merge_configure_dhcp_param,
            wait=False,
        )
        return subnet

    async def update(
        self, id: int, resource: CreateOrUpdateResource
    ) -> Subnet | None:
        subnet = await self.subnets_repository.update(id, resource)
        if subnet:
            self.temporal_service.register_or_update_workflow_call(
                CONFIGURE_DHCP_WORKFLOW_NAME,
                ConfigureDHCPParam(subnet_ids=[subnet.id]),
                parameter_merge_func=merge_configure_dhcp_param,
                wait=False,
            )
        return subnet

    async def delete(self, id: int) -> None:
        subnet = await self.subnets_repository.find_by_id(id=id)
        await self.subnets_repository.delete(id)
        if subnet:
            self.temporal_service.register_or_update_workflow_call(
                CONFIGURE_DHCP_WORKFLOW_NAME,
                ConfigureDHCPParam(
                    vlan_ids=[subnet.vlan_id]
                ),  # use parent when object is deleted
                parameter_merge_func=merge_configure_dhcp_param,
                wait=False,
            )
