# Copyright 2024-2025 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from ipaddress import IPv4Address, IPv6Address
from typing import List

from maascommon.enums.dns import DnsUpdateAction
from maascommon.enums.subnet import RdnsMode
from maascommon.workflows.dhcp import (
    CONFIGURE_DHCP_WORKFLOW_NAME,
    ConfigureDHCPParam,
    merge_configure_dhcp_param,
)
from maasservicelayer.builders.subnets import SubnetBuilder
from maasservicelayer.context import Context
from maasservicelayer.db.filters import QuerySpec
from maasservicelayer.db.repositories.dhcpsnippets import (
    DhcpSnippetsClauseFactory,
)
from maasservicelayer.db.repositories.ipranges import IPRangeClauseFactory
from maasservicelayer.db.repositories.nodegrouptorackcontrollers import (
    NodeGroupToRackControllersClauseFactory,
)
from maasservicelayer.db.repositories.reservedips import (
    ReservedIPsClauseFactory,
)
from maasservicelayer.db.repositories.staticipaddress import (
    StaticIPAddressClauseFactory,
)
from maasservicelayer.db.repositories.staticroutes import (
    StaticRoutesClauseFactory,
)
from maasservicelayer.db.repositories.subnets import SubnetsRepository
from maasservicelayer.models.subnets import Subnet
from maasservicelayer.services.base import BaseService
from maasservicelayer.services.dhcpsnippets import DhcpSnippetsService
from maasservicelayer.services.dnspublications import DNSPublicationsService
from maasservicelayer.services.ipranges import IPRangesService
from maasservicelayer.services.nodegrouptorackcontrollers import (
    NodeGroupToRackControllersService,
)
from maasservicelayer.services.reservedips import ReservedIPsService
from maasservicelayer.services.staticipaddress import StaticIPAddressService
from maasservicelayer.services.staticroutes import StaticRoutesService
from maasservicelayer.services.temporal import TemporalService


class SubnetsService(BaseService[Subnet, SubnetsRepository, SubnetBuilder]):
    def __init__(
        self,
        context: Context,
        temporal_service: TemporalService,
        staticipaddress_service: StaticIPAddressService,
        ipranges_service: IPRangesService,
        staticroutes_service: StaticRoutesService,
        reservedips_service: ReservedIPsService,
        dhcpsnippets_service: DhcpSnippetsService,
        nodegrouptorackcontrollers_service: NodeGroupToRackControllersService,
        dnspublications_service: DNSPublicationsService,
        subnets_repository: SubnetsRepository,
    ):
        super().__init__(context, subnets_repository)
        self.temporal_service = temporal_service
        self.staticipaddress_service = staticipaddress_service
        self.ipranges_service = ipranges_service
        self.staticroutes_service = staticroutes_service
        self.reservedips_service = reservedips_service
        self.dhcpsnippets_service = dhcpsnippets_service
        self.nodegrouptorackcontrollers = nodegrouptorackcontrollers_service
        self.dnspublications_service = dnspublications_service

    async def find_best_subnet_for_ip(
        self, ip: IPv4Address | IPv6Address
    ) -> Subnet | None:
        return await self.repository.find_best_subnet_for_ip(ip)

    async def post_create_hook(self, resource: Subnet) -> None:
        # TODO: proxy workflow
        self.temporal_service.register_or_update_workflow_call(
            CONFIGURE_DHCP_WORKFLOW_NAME,
            ConfigureDHCPParam(subnet_ids=[resource.id]),
            parameter_merge_func=merge_configure_dhcp_param,
            wait=False,
        )

        if resource.rdns_mode != RdnsMode.DISABLED:
            await self.dnspublications_service.create_for_config_update(
                source=f"added subnet {resource.cidr}",
                action=DnsUpdateAction.RELOAD,
                zone="",
                label="",
                rtype="",
            )

    async def post_update_hook(
        self, old_resource: Subnet, updated_resource: Subnet
    ) -> None:
        # TODO: proxy workflow
        self.temporal_service.register_or_update_workflow_call(
            CONFIGURE_DHCP_WORKFLOW_NAME,
            ConfigureDHCPParam(subnet_ids=[updated_resource.id]),
            parameter_merge_func=merge_configure_dhcp_param,
            wait=False,
        )

        if (
            old_resource.rdns_mode != RdnsMode.DISABLED
            or updated_resource.rdns_mode != RdnsMode.DISABLED
        ):
            if old_resource.cidr != updated_resource.cidr:
                await self.dnspublications_service.create_for_config_update(
                    source=f"subnet {old_resource.cidr} changed to {updated_resource.cidr}",
                    action=DnsUpdateAction.RELOAD,
                    zone="",
                    label="",
                    rtype="",
                )
            if old_resource.rdns_mode != updated_resource.rdns_mode:
                await self.dnspublications_service.create_for_config_update(
                    source=f"subnet {updated_resource.cidr} rdns changed to {updated_resource.rdns_mode}",
                    action=DnsUpdateAction.RELOAD,
                    zone="",
                    label="",
                    rtype="",
                )
            if old_resource.allow_dns != updated_resource.allow_dns:
                await self.dnspublications_service.create_for_config_update(
                    source=f"subnet {updated_resource.cidr} allow_dns changed to {updated_resource.allow_dns}",
                    action=DnsUpdateAction.RELOAD,
                    zone="",
                    label="",
                    rtype="",
                )

    async def post_update_many_hook(self, resources: List[Subnet]) -> None:
        raise NotImplementedError("Not implemented yet.")

    async def post_delete_hook(self, resource: Subnet) -> None:
        # cascade delete
        await self.staticipaddress_service.delete_many(
            query=QuerySpec(
                where=StaticIPAddressClauseFactory.with_subnet_id(resource.id)
            )
        )
        await self.ipranges_service.delete_many(
            query=QuerySpec(
                where=IPRangeClauseFactory.with_subnet_id(resource.id)
            )
        )
        await self.staticroutes_service.delete_many(
            query=QuerySpec(
                where=StaticRoutesClauseFactory.or_clauses(
                    [
                        StaticRoutesClauseFactory.with_source_id(resource.id),
                        StaticRoutesClauseFactory.with_destination_id(
                            resource.id
                        ),
                    ]
                )
            )
        )
        await self.reservedips_service.delete_many(
            query=QuerySpec(
                where=ReservedIPsClauseFactory.with_subnet_id(resource.id)
            )
        )
        await self.dhcpsnippets_service.delete_many(
            query=QuerySpec(
                where=DhcpSnippetsClauseFactory.with_subnet_id(resource.id)
            )
        )
        await self.nodegrouptorackcontrollers.delete_many(
            query=QuerySpec(
                where=NodeGroupToRackControllersClauseFactory.with_subnet_id(
                    resource.id
                )
            )
        )
        # TODO: proxy workflow
        self.temporal_service.register_or_update_workflow_call(
            CONFIGURE_DHCP_WORKFLOW_NAME,
            ConfigureDHCPParam(
                vlan_ids=[resource.vlan_id]
            ),  # use parent when object is deleted
            parameter_merge_func=merge_configure_dhcp_param,
            wait=False,
        )
        if resource.rdns_mode != RdnsMode.DISABLED:
            await self.dnspublications_service.create_for_config_update(
                source=f"removed subnet {resource.cidr}",
                action=DnsUpdateAction.RELOAD,
                zone="",
                label="",
                rtype="",
            )

    async def post_delete_many_hook(self, resources: List[Subnet]) -> None:
        raise NotImplementedError("Not implemented yet.")
