import pytest
from sqlalchemy.ext.asyncio import AsyncConnection

from maasservicelayer.db.repositories.staticipaddress import (
    StaticIPAddressRepository,
)
from tests.fixtures.factories.interface import create_test_interface_entry
from tests.fixtures.factories.staticipaddress import (
    create_test_staticipaddress_entry,
)
from tests.fixtures.factories.subnet import create_test_subnet_entry
from tests.maasapiserver.fixtures.db import Fixture


@pytest.mark.asyncio
class TestStaticIPAddressRepository:
    async def test_get_discovered_ips_in_family_for_interfaces(
        self, db_connection: AsyncConnection, fixture: Fixture
    ) -> None:
        v4_subnet = await create_test_subnet_entry(fixture, cidr="10.0.0.0/24")
        v6_subnet = await create_test_subnet_entry(
            fixture, cidr="fd42:be3f:b08a:3d6c::/64"
        )
        v4_addrs = [
            (
                await create_test_staticipaddress_entry(
                    fixture, subnet=v4_subnet, alloc_type=6
                )
            )[0]
            for _ in range(3)
        ]
        v6_addrs = [
            (
                await create_test_staticipaddress_entry(
                    fixture, subnet=v6_subnet, alloc_type=6
                )
            )[0]
            for _ in range(3)
        ]
        interfaces = [
            await create_test_interface_entry(fixture, ips=v4_addrs + v6_addrs)
            for _ in range(3)
        ]

        staticipaddress_repository = StaticIPAddressRepository(db_connection)
        result = await staticipaddress_repository.get_discovered_ips_in_family_for_interfaces(
            interfaces, family=4
        )

        assert {addr.id for addr in result} == {
            addr["id"] for addr in v4_addrs
        }
