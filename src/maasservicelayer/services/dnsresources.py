#  Copyright 2024 Canonical Ltd.  This software is licensed under the
#  GNU Affero General Public License version 3 (see the file LICENSE).

from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncConnection

from maascommon.enums.ipaddress import IpAddressType
from maasservicelayer.db.repositories.dnsresources import DNSResourceRepository
from maasservicelayer.models.dnsresources import DNSResource
from maasservicelayer.models.staticipaddress import StaticIPAddress
from maasservicelayer.services._base import Service
from maasservicelayer.services.domains import DomainsService
from provisioningserver.utils.network import coerce_to_valid_hostname


class DNSResourcesService(Service):
    def __init__(
        self,
        connection: AsyncConnection,
        domains_service: DomainsService,
        dnsresource_repository: Optional[DNSResourceRepository] = None,
    ):
        super().__init__(connection)
        self.domains_service = domains_service
        self.dnsresource_repository = (
            dnsresource_repository
            if dnsresource_repository
            else DNSResourceRepository(connection)
        )

    async def get_or_create(
        self, **values: dict[str, Any]
    ) -> (DNSResource, bool):
        if "domain_id" not in values:
            default_domain = await self.domains_service.get_default_domain()
            values["domain_id"] = default_domain.id

        dnsrr = await self.dnsresource_repository.get(**values)
        if dnsrr is None:
            dnsrr = await self.dnsresource_repository.create(**values)
            return (dnsrr, True)
        return (dnsrr, False)

    async def release_dynamic_hostname(
        self, ip: StaticIPAddress, but_not_for: Optional[DNSResource] = None
    ) -> None:
        if ip.ip is None or ip.alloc_type != IpAddressType.DISCOVERED.value:
            return

        default_domain = await self.domains_service.get_default_domain()

        resources = await self.dnsresource_repository.get_dnsresources_in_domain_for_ip(
            default_domain, ip
        )

        for dnsrr in resources:
            result = await self.dnsresource_repository.get_ips_for_dnsresource(
                dnsrr, discovered_only=True, matching=ip
            )

            ip_ids = [row.id for row in result]

            if ip.id in ip_ids:
                await self.dnsresource_repository.remove_ip_relation(dnsrr, ip)

            find_remaining_relations_stmt = (
                select(DNSResourceIPAddressTable.c.id)
                .select_from(DNSResourceIPAddressTable)
                .filter(DNSResourceIPAddressTable.c.dnsresource_id == dnsrr.id)
            )

            remaining_relations = (
                await self.dnsresource_repository.get_ips_for_dnsresource(
                    dnsrr
                )
            )
            if len(remaining_relations) == 0:
                await self.dnsresource_repository.delete(dnsrr)

    async def update_dynamic_hostname(
        self, ip: StaticIPAddress, hostname: str
    ) -> None:
        hostname = coerce_to_valid_hostname(hostname)

        await self.release_dynamic_hostname(ip)

        dnsrr, created = await self.get_or_create(name=hostname)
        if created:
            self.dnsresource_repository.link_ip(dnsrr, ip)
