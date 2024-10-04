#  Copyright 2024 Canonical Ltd.  This software is licensed under the
#  GNU Affero General Public License version 3 (see the file LICENSE).

from typing import Any

from netaddr import IPAddress
from sqlalchemy import desc, select, Select, text
from sqlalchemy.sql.operators import eq, le

from maasservicelayer.db.filters import QuerySpec
from maasservicelayer.db.repositories.base import (
    BaseRepository,
    CreateOrUpdateResource,
)
from maasservicelayer.db.tables import SubnetTable
from maasservicelayer.models.base import ListResult
from maasservicelayer.models.subnets import Subnet


class SubnetsRepository(BaseRepository[Subnet]):
    async def create(self, resource: CreateOrUpdateResource) -> Subnet:
        raise NotImplementedError()

    async def find_by_id(self, id: int) -> Subnet | None:
        stmt = self._select_all_statement().filter(eq(SubnetTable.c.id, id))

        result = await self.connection.execute(stmt)
        subnet = result.first()
        if not subnet:
            return None
        return Subnet(**subnet._asdict())

    async def find_best_subnet_for_ip(self, ip: str) -> Subnet | None:
        ip_addr = IPAddress(ip)
        if ip_addr.is_ipv4_mapped():
            ip_addr = ip.ipv4()

        stmt = text(
            """
            SELECT DISTINCT
                subnet.*,
                masklen(subnet.cidr) "prefixlen",
                vlan.dhcp_on "dhcp_on"
            FROM maasserver_subnet AS subnet
            INNER JOIN maasserver_vlan AS vlan
                ON subnet.vlan_id = vlan.id
            WHERE
                :ip << subnet.cidr /* Specified IP is inside range */
            ORDER BY
                /* Pick subnet that is on a VLAN that is managed over a subnet
                   that is not managed on a VLAN. */
                dhcp_on DESC,
                /* If there are multiple subnets we want to pick the most specific
                   one that the IP address falls within. */
                prefixlen DESC
            LIMIT 1
        """
        )

        result = (
            await self.connection.execute(stmt, {"ip": ip_addr})
        ).one_or_none()
        if not result:
            return None

        res = result._asdict()
        del res["prefixlen"]
        del res["dhcp_on"]
        return Subnet(**res)

    async def find_by_name(self, name: str) -> Subnet | None:
        raise NotImplementedError()

    async def list(
        self, token: str | None, size: int, query: QuerySpec | None = None
    ) -> ListResult[Subnet]:
        # TODO: use the query for the filters
        stmt = (
            self._select_all_statement()
            .order_by(desc(SubnetTable.c.id))
            .limit(size + 1)  # Retrieve one more element to get the next token
        )
        if token is not None:
            stmt = stmt.where(le(SubnetTable.c.id, int(token)))

        result = (await self.connection.execute(stmt)).all()
        next_token = None
        if len(result) > size:  # There is another page
            next_token = result.pop().id
        return ListResult[Subnet](
            items=[Subnet(**row._asdict()) for row in result],
            next_token=next_token,
        )

    async def update(
        self, id: int, resource: CreateOrUpdateResource
    ) -> Subnet:
        raise NotImplementedError()

    async def delete(self, id: int) -> None:
        raise NotImplementedError()

    def _select_all_statement(self) -> Select[Any]:
        return select(
            SubnetTable.c.id,
            SubnetTable.c.created,
            SubnetTable.c.updated,
            SubnetTable.c.name,
            SubnetTable.c.cidr,
            SubnetTable.c.gateway_ip,
            SubnetTable.c.dns_servers,
            SubnetTable.c.rdns_mode,
            SubnetTable.c.allow_proxy,
            SubnetTable.c.description,
            SubnetTable.c.active_discovery,
            SubnetTable.c.managed,
            SubnetTable.c.allow_dns,
            SubnetTable.c.disabled_boot_architectures,
        ).select_from(SubnetTable)
