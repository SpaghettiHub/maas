#  Copyright 2024-2025 Canonical Ltd.  This software is licensed under the
#  GNU Affero General Public License version 3 (see the file LICENSE).

from typing import List, Optional

from maascommon.enums.ipaddress import IpAddressFamily, IpAddressType
from maascommon.workflows.dhcp import (
    CONFIGURE_DHCP_WORKFLOW_NAME,
    ConfigureDHCPParam,
    merge_configure_dhcp_param,
)
from maasservicelayer.context import Context
from maasservicelayer.db.filters import QuerySpec
from maasservicelayer.db.repositories.staticipaddress import (
    StaticIPAddressClauseFactory,
    StaticIPAddressRepository,
)
from maasservicelayer.models.fields import MacAddress
from maasservicelayer.models.interfaces import Interface
from maasservicelayer.models.staticipaddress import (
    StaticIPAddress,
    StaticIPAddressBuilder,
)
from maasservicelayer.models.subnets import Subnet
from maasservicelayer.services._base import BaseService
from maasservicelayer.services.temporal import TemporalService


class StaticIPAddressService(
    BaseService[
        StaticIPAddress, StaticIPAddressRepository, StaticIPAddressBuilder
    ]
):
    def __init__(
        self,
        context: Context,
        temporal_service: TemporalService,
        staticipaddress_repository: StaticIPAddressRepository,
    ):
        super().__init__(context, staticipaddress_repository)
        self.temporal_service = temporal_service

    async def post_create_hook(self, resource: StaticIPAddress) -> None:
        if resource.alloc_type != IpAddressType.DISCOVERED:
            self.temporal_service.register_or_update_workflow_call(
                CONFIGURE_DHCP_WORKFLOW_NAME,
                ConfigureDHCPParam(static_ip_addr_ids=[resource.id]),
                parameter_merge_func=merge_configure_dhcp_param,
                wait=False,
            )
        return

    async def post_update_hook(
        self, old_resource: StaticIPAddress, updated_resource: StaticIPAddress
    ) -> None:
        if self._update_should_trigger_workflow(
            old_resource, updated_resource
        ):
            self.temporal_service.register_or_update_workflow_call(
                CONFIGURE_DHCP_WORKFLOW_NAME,
                ConfigureDHCPParam(static_ip_addr_ids=[updated_resource.id]),
                parameter_merge_func=merge_configure_dhcp_param,
                wait=False,
            )
        return

    async def post_update_many_hook(
        self,
        old_resources: List[StaticIPAddress],
        updated_resources: List[StaticIPAddress],
    ) -> None:
        old_resources = sorted(old_resources, key=lambda obj: obj.id)
        updated_resources = sorted(updated_resources, key=lambda obj: obj.id)
        for old, updated in zip(old_resources, updated_resources):
            if self._update_should_trigger_workflow(old, updated):
                raise NotImplementedError("Not implemented yet.")

    async def create_or_update(
        self, builder: StaticIPAddressBuilder
    ) -> StaticIPAddress:
        ip = await self.repository.create_or_update(builder)
        if ip.alloc_type != IpAddressType.DISCOVERED:
            self.temporal_service.register_or_update_workflow_call(
                CONFIGURE_DHCP_WORKFLOW_NAME,
                ConfigureDHCPParam(static_ip_addr_ids=[ip.id]),
                parameter_merge_func=merge_configure_dhcp_param,
                wait=False,
            )
        return ip

    async def post_delete_hook(self, resource: StaticIPAddress) -> None:
        if resource.alloc_type != IpAddressType.DISCOVERED:
            self.temporal_service.register_or_update_workflow_call(
                CONFIGURE_DHCP_WORKFLOW_NAME,
                ConfigureDHCPParam(
                    subnet_ids=[resource.subnet_id]
                ),  # use parent id on delete
                parameter_merge_func=merge_configure_dhcp_param,
                wait=False,
            )

    async def post_delete_many_hook(
        self, resources: List[StaticIPAddress]
    ) -> None:
        raise NotImplementedError("Not implemented yet.")

    async def get_discovered_ips_in_family_for_interfaces(
        self,
        interfaces: list[Interface],
        family: IpAddressFamily = IpAddressFamily.IPV4,
    ) -> List[StaticIPAddress]:
        return (
            await self.repository.get_discovered_ips_in_family_for_interfaces(
                interfaces, family=family
            )
        )

    async def get_for_interfaces(
        self,
        interfaces: list[Interface],
        subnet: Optional[Subnet] = None,
        ip: Optional[StaticIPAddress] = None,
        alloc_type: Optional[int] = None,
    ) -> StaticIPAddress | None:
        return await self.repository.get_for_interfaces(
            interfaces, subnet=subnet, ip=ip, alloc_type=alloc_type
        )

    async def get_for_nodes(self, query: QuerySpec) -> list[StaticIPAddress]:
        return await self.repository.get_for_nodes(query=query)

    async def get_mac_addresses(self, query: QuerySpec) -> list[MacAddress]:
        return await self.repository.get_mac_addresses(query=query)

    def _update_should_trigger_workflow(
        self, old_resource: StaticIPAddress, updated_resource: StaticIPAddress
    ) -> bool:
        if (
            old_resource.ip != updated_resource.ip
            or old_resource.alloc_type != updated_resource.alloc_type
            or old_resource.subnet_id != updated_resource.subnet_id
            and updated_resource.alloc_type != IpAddressType.DISCOVERED
        ):
            return True
        return False

    async def get_staticips_for_user(
        self, user_id: int
    ) -> list[StaticIPAddress]:
        return await self.get_many(
            query=QuerySpec(
                where=StaticIPAddressClauseFactory.with_user_id(user_id)
            )
        )
