#  Copyright 2024-2025 Canonical Ltd.  This software is licensed under the
#  GNU Affero General Public License version 3 (see the file LICENSE).

from typing import List

from maascommon.enums.dns import DnsUpdateAction
from maascommon.enums.ipaddress import IpAddressType
from maascommon.workflows.dhcp import (
    CONFIGURE_DHCP_WORKFLOW_NAME,
    ConfigureDHCPParam,
    merge_configure_dhcp_param,
)
from maasservicelayer.context import Context
from maasservicelayer.db.repositories.interfaces import InterfaceRepository
from maasservicelayer.models.base import ListResult
from maasservicelayer.models.interfaces import Interface
from maasservicelayer.models.nodes import Node
from maasservicelayer.models.staticipaddress import StaticIPAddress
from maasservicelayer.services._base import Service
from maasservicelayer.services.dnspublications import DNSPublicationsService
from maasservicelayer.services.dnsresources import DNSResourcesService
from maasservicelayer.services.domains import DomainsService
from maasservicelayer.services.temporal import TemporalService


class InterfacesService(Service):
    def __init__(
        self,
        context: Context,
        temporal_service: TemporalService,
        dnsresource_service: DNSResourcesService,
        dnspublication_service: DNSPublicationsService,
        domain_service: DomainsService,
        interface_repository: InterfaceRepository,
    ):
        super().__init__(context)
        self.temporal_service = temporal_service
        self.dnsresource_service = dnsresource_service
        self.dnspublication_service = dnspublication_service
        self.domain_service = domain_service
        self.interface_repository = interface_repository

    async def list(
        self, node_id: int, page: int, size: int
    ) -> ListResult[Interface]:
        return await self.interface_repository.list(
            node_id=node_id, page=page, size=size
        )

    async def get_interfaces_for_mac(self, mac: str) -> List[Interface]:
        return await self.interface_repository.get_interfaces_for_mac(mac)

    async def get_interfaces_in_fabric(
        self, fabric_id: int
    ) -> List[Interface]:
        return await self.interface_repository.get_interfaces_in_fabric(
            fabric_id=fabric_id
        )

    async def bulk_link_ip(
        self, sip: StaticIPAddress, interfaces: List[Interface]
    ) -> None:
        for interface in interfaces:
            await self.interface_repository.add_ip(interface, sip)

    def _get_dns_label_for_interface(
        self, interface: Interface, node: Node
    ) -> str:
        if node.boot_interface_id == interface.id:
            return node.hostname
        else:
            return f"{interface.name}.{node.hostname}"

    async def add_ip(self, interface: Interface, sip: StaticIPAddress) -> None:
        await self.interface_repository.add_ip(interface, sip)

        if sip.alloc_type in (
            IpAddressType.AUTO,
            IpAddressType.STICKY,
            IpAddressType.USER_RESERVED,
        ):
            self.temporal_service.register_or_update_workflow_call(
                CONFIGURE_DHCP_WORKFLOW_NAME,
                ConfigureDHCPParam(static_ip_addr_ids=[sip.id]),
                parameter_merge_func=merge_configure_dhcp_param,
                wait=False,
            )

        node = await self.interface_repository.get_node_for_interface(
            interface
        )
        if not node:
            return

        dns_label = self._get_dns_label_for_interface(interface, node)
        domain = await self.domain_service.get_domain_for_node(node)

        await self.dnsresource_service.add_ip(sip, dns_label, domain)

        await self.dnspublication_service.create_for_config_update(
            source=f"ip {sip.ip} connected to {node.hostname} on {interface.name}",
            action=DnsUpdateAction.INSERT,
            label=dns_label,
            rtype="A",
            zone=domain.name,
        )

    async def remove_ip(
        self, interface: Interface, sip: StaticIPAddress
    ) -> None:
        await self.interface_repository.remove_ip(interface, sip)

        if sip.alloc_type in (
            IpAddressType.AUTO,
            IpAddressType.STICKY,
            IpAddressType.USER_RESERVED,
        ):
            self.temporal_service.register_or_update_workflow_call(
                CONFIGURE_DHCP_WORKFLOW_NAME,
                ConfigureDHCPParam(subnet_ids=[sip.subnet_id]),
                parameter_merge_func=merge_configure_dhcp_param,
                wait=False,
            )

        node = await self.interface_repository.get_node_for_interface(
            interface
        )
        if not node:
            return

        dns_label = self._get_dns_label_for_interface(interface, node)
        domain = await self.domain_service.get_domain_for_node(node)

        should_delete = await self.dnsresource_service.remove_ip(
            sip, dns_label, domain
        )

        await self.dnspublication_service.create_for_config_update(
            source=f"ip {sip.ip} disconnected from {node.hostname} on {interface.name}",
            action=(
                DnsUpdateAction.DELETE
                if should_delete
                else DnsUpdateAction.UPDATE
            ),
            label=dns_label,
            rtype="A",
            zone=domain.name,
        )
