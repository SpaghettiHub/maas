import pytest
from sqlalchemy.ext.asyncio import AsyncConnection

from maascommon.enums.ipaddress import IpAddressType
from maasservicelayer.models.staticipaddress import StaticIPAddress
from maasservicelayer.models.subnets import Subnet
from maasservicelayer.services.ipranges import IPRangesService
from tests.fixtures.factories.iprange import create_test_ip_range_entry
from tests.fixtures.factories.staticipaddress import (
    create_test_staticipaddress_entry,
)
from tests.fixtures.factories.subnet import create_test_subnet_entry
from tests.maasapiserver.fixtures.db import Fixture


@pytest.mark.asyncio
class TestIPRangesService:
    async def test_get_dynamic_range_for_ip(
        self, db_connection: AsyncConnection, fixture: Fixture
    ) -> None:
        subnet = await create_test_subnet_entry(fixture, cidr="10.0.0.0/24")
        dyn_range = await create_test_ip_range_entry(
            fixture, subnet=subnet, offset=0, size=5
        )
        sip = (
            await create_test_staticipaddress_entry(
                fixture,
                subnet=subnet,
                ip="10.0.0.2",
                alloc_type=IpAddressType.DISCOVERED.value,
            )
        )[0]

        ipranges_service = IPRangesService(db_connection)

        result = await ipranges_service.get_dynamic_range_for_ip(
            Subnet(**subnet), StaticIPAddress(**sip)
        )

        assert result.id == dyn_range["id"]
