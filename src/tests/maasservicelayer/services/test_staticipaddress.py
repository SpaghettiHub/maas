from datetime import datetime

from netaddr import IPNetwork
import pytest
from sqlalchemy.ext.asyncio import AsyncConnection

from maascommon.enums.ipaddress import IpAddressFamily, IpAddressType
from maasservicelayer.models.subnets import Subnet
from maasservicelayer.services.staticipaddress import StaticIPAddressService
from tests.fixtures.factories.interface import create_test_interface_entry
from tests.fixtures.factories.staticipaddress import (
    create_test_staticipaddress_entry,
)
from tests.fixtures.factories.subnet import create_test_subnet_entry
from tests.maasapiserver.fixtures.db import Fixture


@pytest.mark.asyncio
class TestStaticIPAddressService:
    async def test_create_or_update_create(
        self, db_connection: AsyncConnection, fixture: Fixture
    ) -> None:
        subnet = await create_test_subnet_entry(fixture, cidr="10.0.0.0/24")

        staticipaddress_service = StaticIPAddressService(db_connection)

        now = datetime.utcnow()

        sip = await staticipaddress_service.create_or_update(
            ip="10.0.0.2",
            lease_time=30,
            alloc_type=IpAddressType.DISCOVERED,
            subnet_id=subnet["id"],
            created=now,
            updated=now,
        )

        assert sip is not None

    async def test_create_or_update_update(
        self, db_connection: AsyncConnection, fixture: Fixture
    ) -> None:
        subnet = await create_test_subnet_entry(fixture)
        sip = (
            await create_test_staticipaddress_entry(
                fixture,
                subnet=subnet,
                alloc_type=IpAddressType.DISCOVERED.value,
            )
        )[0]

        staticipaddress_service = StaticIPAddressService(db_connection)

        now = datetime.utcnow()

        new_sip = await staticipaddress_service.create_or_update(
            ip=str(sip["ip"]),
            lease_time=30,
            alloc_type=IpAddressType.DISCOVERED,
            subnet_id=subnet["id"],
            created=None,
            updated=now,
        )

        assert new_sip.id == sip["id"]
        assert new_sip.lease_time != sip["lease_time"]
        assert new_sip.created == sip["created"]
        assert new_sip.ip == sip["ip"]
        assert new_sip.updated != sip["updated"]
        assert new_sip.alloc_type == sip["alloc_type"]

    async def test_get_discovered_ips_in_family_for_interfaces(
        self, db_connection: AsyncConnection, fixture: Fixture
    ) -> None:
        subnet = await create_test_subnet_entry(fixture)
        sips = [
            (
                await create_test_staticipaddress_entry(
                    fixture,
                    subnet=subnet,
                    alloc_type=IpAddressType.DISCOVERED.value,
                )
            )[0]
            for _ in range(3)
        ]
        interfaces = [
            await create_test_interface_entry(fixture, ips=sips)
            for _ in range(3)
        ]

        staticipaddress_service = StaticIPAddressService(db_connection)

        subnet_network = IPNetwork(str(subnet["cidr"]))
        result = await staticipaddress_service.get_discovered_ips_in_family_for_interfaces(
            interfaces,
            family=(
                IpAddressFamily.IPV4
                if subnet_network.version == IpAddressFamily.IPV4.value
                else IpAddressFamily.IPV6
            ),
        )

        assert {sip["id"] for sip in sips} == {sip.id for sip in result}

    async def test_get_for_interfaces(
        self, db_connection: AsyncConnection, fixture: Fixture
    ) -> None:
        subnet = await create_test_subnet_entry(fixture)
        sip = (
            await create_test_staticipaddress_entry(
                fixture,
                subnet=subnet,
                alloc_type=IpAddressType.DISCOVERED.value,
            )
        )[0]
        interfaces = [
            await create_test_interface_entry(fixture, ips=[sip])
            for _ in range(3)
        ]

        staticipaddress_service = StaticIPAddressService(db_connection)

        result = await staticipaddress_service.get_for_interfaces(
            interfaces,
            subnet=Subnet(**subnet),
            alloc_type=IpAddressType.DISCOVERED,
        )

        assert sip["id"] == result.id

    async def test_create(
        self, db_connection: AsyncConnection, fixture: Fixture
    ) -> None:
        subnet = await create_test_subnet_entry(fixture, cidr="10.0.0.0/24")

        staticipaddress_service = StaticIPAddressService(db_connection)

        now = datetime.utcnow()

        result = await staticipaddress_service.create(
            ip="10.0.0.2",
            lease_time=30,
            alloc_type=IpAddressType.DISCOVERED,
            subnet_id=subnet["id"],
            created=now,
            updated=now,
        )

        assert result is not None
        assert str(result.ip) == "10.0.0.2"
        assert result.alloc_type == IpAddressType.DISCOVERED.value
        assert result.subnet_id == subnet["id"]

    async def test_update(
        self, db_connection: AsyncConnection, fixture: Fixture
    ) -> None:
        subnet = await create_test_subnet_entry(fixture)
        sip = (
            await create_test_staticipaddress_entry(
                fixture,
                subnet=subnet,
                alloc_type=IpAddressType.DISCOVERED.value,
            )
        )[0]

        staticipaddress_service = StaticIPAddressService(db_connection)

        now = datetime.utcnow()

        sip_copy = sip.copy()
        sip_copy["alloc_type"] = IpAddressType.DISCOVERED
        sip_copy["updated"] = now
        sip_copy["lease_time"] = 30
        del sip_copy["user_id"]

        result = await staticipaddress_service.update(**sip_copy)

        assert sip["id"] == result.id
        assert sip["ip"] == result.ip
        assert sip["alloc_type"] == result.alloc_type.value
        assert sip["created"] == result.created
        assert sip["lease_time"] != result.lease_time
        assert sip["updated"] != result.updated
