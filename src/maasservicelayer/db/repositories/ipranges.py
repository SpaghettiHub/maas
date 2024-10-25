import netaddr
from pydantic import IPvAnyAddress
from sqlalchemy import select

from maasservicelayer.db.filters import QuerySpec
from maasservicelayer.db.repositories.base import (
    BaseRepository,
    CreateOrUpdateResource,
    CreateOrUpdateResourceBuilder,
)
from maasservicelayer.db.tables import IPRangeTable, SubnetTable
from maasservicelayer.models.base import ListResult
from maasservicelayer.models.ipranges import IPRange
from maasservicelayer.models.subnets import Subnet


class IPRangesResourceBuilder(CreateOrUpdateResourceBuilder):
    def with_type(self, type: str) -> "IPRangesResourceBuilder":
        self._request.set_value(IPRangeTable.c.type, type)
        return self

    def with_start_ip(self, ip: IPvAnyAddress) -> "IPRangesResourceBuilder":
        self._request.set_value(IPRangeTable.c.start_ip, str(ip))
        return self

    def with_end_ip(self, ip: IPvAnyAddress) -> "IPRangesResourceBuilder":
        self._request.set_value(IPRangeTable.c.end_ip, str(ip))
        return self

    def with_comment(self, comment: str) -> "IPRangesResourceBuilder":
        self._request.set_value(IPRangeTable.c.comment, comment)
        return self

    def with_subnet_id(self, id: int) -> "IPRangesResourceBuilder":
        self._request.set_value(IPRangeTable.c.subnet_id, id)
        return self


class IPRangesRepository(BaseRepository):
    async def delete(self, id: int) -> None:
        raise NotImplementedError("Not implemented yet.")

    async def find_by_id(self, id: int) -> IPRange | None:
        raise NotImplementedError("Not implemented yet.")

    async def list(
        self, token: str | None, size: int, query: QuerySpec | None = None
    ) -> ListResult[IPRange]:
        raise NotImplementedError("Not implemented yet.")

    async def create(self, resource: CreateOrUpdateResource) -> IPRange:
        raise NotImplementedError("Not implemented yet.")

    async def update(
        self, id: int, resource: CreateOrUpdateResource
    ) -> IPRange:
        raise NotImplementedError("Not implemented yet.")

    async def get_dynamic_range_for_ip(
        self, subnet: Subnet, ip: IPvAnyAddress
    ) -> IPRange | None:
        stmt = (
            select(IPRangeTable)
            .select_from(IPRangeTable)
            .join(
                SubnetTable,
                SubnetTable.c.id == IPRangeTable.c.subnet_id,
            )
            .filter(SubnetTable.c.id == subnet.id)
        )

        result = (await self.connection.execute(stmt)).all()

        ipranges = [IPRange(**row._asdict()) for row in result]

        netaddr_ip = netaddr.IPAddress(str(ip))

        for iprange in ipranges:
            if netaddr_ip in netaddr.IPRange(
                str(iprange.start_ip), str(iprange.end_ip)
            ):
                return iprange

        return None
