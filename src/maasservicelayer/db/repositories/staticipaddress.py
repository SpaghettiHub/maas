from sqlalchemy import bindparam, insert, text, update
from sqlalchemy.ext.asyncio import AsyncConnection

from maascommon.enums.ipaddress import IpAddressFamily
from maasservicelayer.db.repositories.base import CreateOrUpdateResource
from maasservicelayer.db.tables import StaticIPAddressTable
from maasservicelayer.models.interfaces import Interface
from maasservicelayer.models.staticipaddress import StaticIPAddress

STATICIPADDRESS_FIELDS = [
    StaticIPAddressTable.c.id,
    StaticIPAddressTable.c.ip,
    StaticIPAddressTable.c.alloc_type,
    StaticIPAddressTable.c.lease_time,
    StaticIPAddressTable.c.temp_expires_on,
    StaticIPAddressTable.c.created,
    StaticIPAddressTable.c.updated,
]


class StaticIPAddressRepository:
    def __init__(self, connection: AsyncConnection):
        self.connection = connection

    async def create(
        self, resource: CreateOrUpdateResource
    ) -> StaticIPAddress:
        stmt = (
            insert(StaticIPAddressTable)
            .returning(*STATICIPADDRESS_FIELDS)
            .values(**resource.get_values())
        )

        result = (await self.connection.execute(stmt)).one()
        return StaticIPAddress(**result._asdict())

    async def update(
        self, id: int, resource: CreateOrUpdateResource
    ) -> StaticIPAddress:
        stmt = (
            update(StaticIPAddressTable)
            .where(StaticIPAddressTable.c.id == id)
            .returning(*STATICIPADDRESS_FIELDS)
            .values(**resource.get_values())
        )

        result = (await self.connection.execute(stmt)).one()
        return StaticIPAddress(**result._asdict())

    async def get_discovered_ips_in_family_for_interfaces(
        self,
        interfaces: list[Interface],
        family: IpAddressFamily = IpAddressFamily.IPV4.value,
    ) -> list[StaticIPAddress]:
        stmt = text(
            """
            SELECT
                ip.*
            FROM maasserver_staticipaddress AS ip
            JOIN maasserver_interface_ip_addresses AS iface_ip ON
                iface_ip.staticipaddress_id = ip.id
            JOIN maasserver_interface AS iface ON
                iface.id = iface_ip.interface_id
            WHERE family(ip.ip) = :family AND iface.id IN :iface_ids AND ip.alloc_type = 6
            """
        )

        stmt = stmt.bindparams(bindparam("iface_ids", expanding=True))

        result = (
            await self.connection.execute(
                stmt,
                {
                    "family": family,
                    "iface_ids": [interface.id for interface in interfaces],
                },
            )
        ).all()

        return [StaticIPAddress(**row._asdict()) for row in result]
