# Copyright 2024 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

import time

from netaddr import IPAddress
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncConnection

from maascommon.enums.ipaddress import IpAddressType
from maasservicelayer.db.tables import (
    InterfaceIPAddressTable,
    InterfaceTable,
    StaticIPAddressTable,
)
from maasservicelayer.services.configurations import ConfigurationsService
from maasservicelayer.services.dnsresources import DNSResourcesService
from maasservicelayer.services.domains import DomainsService
from maasservicelayer.services.interfaces import InterfacesService
from maasservicelayer.services.ipranges import IPRangesService
from maasservicelayer.services.leases import LeasesService, LeaseUpdateError
from maasservicelayer.services.nodes import NodesService
from maasservicelayer.services.secrets import SecretsServiceFactory
from maasservicelayer.services.staticipaddress import StaticIPAddressService
from maasservicelayer.services.subnets import SubnetsService
from tests.fixtures.factories.interface import create_test_interface_entry
from tests.fixtures.factories.iprange import create_test_ip_range_entry
from tests.fixtures.factories.node import create_test_machine_entry
from tests.fixtures.factories.staticipaddress import (
    create_test_staticipaddress_entry,
)
from tests.fixtures.factories.subnet import create_test_subnet_entry
from tests.maasapiserver.fixtures.db import Fixture


@pytest.mark.asyncio
class TestLeasesService:
    async def create_service(
        self, connection: AsyncConnection
    ) -> LeasesService:
        configurations = ConfigurationsService(connection)
        secrets = await SecretsServiceFactory.produce(
            connection=connection, config_service=configurations
        )
        return LeasesService(
            connection,
            DNSResourcesService(
                connection,
                DomainsService(
                    connection,
                ),
            ),
            NodesService(connection, secrets),
            StaticIPAddressService(connection),
            SubnetsService(connection),
            InterfacesService(connection),
            IPRangesService(connection),
        )

    async def test_store_lease_info_invalid_action(
        self, db_connection: AsyncConnection, fixture: Fixture
    ):
        machine = await create_test_machine_entry(fixture)
        interface = await create_test_interface_entry(fixture, node=machine)
        service = await self.create_service(db_connection)

        try:
            await service.store_lease_info(
                "notvalid",
                "ipv4",
                "10.0.0.2",
                interface.mac_address,
                machine["hostname"],
                int(time.time()),
                30,
            )
        except Exception as e:
            assert isinstance(e, LeaseUpdateError)

    async def test_store_lease_info_no_subnet(
        self, db_connection: AsyncConnection, fixture: Fixture
    ):
        machine = await create_test_machine_entry(fixture)
        interface = await create_test_interface_entry(fixture, node=machine)

        service = await self.create_service(db_connection)
        try:
            await service.store_lease_info(
                "commit",
                "ipv4",
                "10.0.0.2",
                interface.mac_address,
                machine["hostname"],
                int(time.time()),
                30,
            )
        except Exception as e:
            assert isinstance(e, LeaseUpdateError)

    async def test_store_lease_info_commit_v4(
        self, db_connection: AsyncConnection, fixture: Fixture
    ) -> None:
        subnet = await create_test_subnet_entry(fixture, cidr="10.0.0.0/24")
        machine = await create_test_machine_entry(fixture)
        interface = await create_test_interface_entry(fixture, node=machine)
        await create_test_ip_range_entry(
            fixture, subnet=subnet, offset=1, size=5, type="dynamic"
        )

        service = await self.create_service(db_connection)
        await service.store_lease_info(
            "commit",
            "ipv4",
            "10.0.0.2",
            interface.mac_address,
            machine["hostname"],
            int(time.time()),
            30,
        )

        stmt = (
            select(
                StaticIPAddressTable.c.id,
                InterfaceTable.c.id,
            )
            .select_from(
                StaticIPAddressTable,
            )
            .join(
                InterfaceIPAddressTable,
                InterfaceIPAddressTable.c.staticipaddress_id
                == StaticIPAddressTable.c.id,
            )
            .join(
                InterfaceTable,
                InterfaceTable.c.id == InterfaceIPAddressTable.c.interface_id,
            )
            .filter(
                StaticIPAddressTable.c.ip == IPAddress("10.0.0.2"),
                StaticIPAddressTable.c.alloc_type
                == IpAddressType.DISCOVERED.value,
            )
        )

        result = (await db_connection.execute(stmt)).all()

        assert len(result) > 0

    async def test_store_lease_info_commit_v6(
        self, db_connection: AsyncConnection, fixture: Fixture
    ) -> None:
        subnet = await create_test_subnet_entry(
            fixture, cidr="fd42:be3f:b08a:3d6c::/64"
        )
        machine = await create_test_machine_entry(fixture)
        interface = await create_test_interface_entry(fixture, node=machine)
        await create_test_ip_range_entry(
            fixture, subnet=subnet, offset=1, size=5, type="dynamic"
        )

        service = await self.create_service(db_connection)
        await service.store_lease_info(
            "commit",
            "ipv6",
            "fd42:be3f:b08a:3d6c::2",
            interface.mac_address,
            machine["hostname"],
            int(time.time()),
            30,
        )

        stmt = (
            select(
                StaticIPAddressTable.c.id,
                InterfaceTable.c.id,
            )
            .select_from(
                StaticIPAddressTable,
            )
            .join(
                InterfaceIPAddressTable,
                InterfaceIPAddressTable.c.staticipaddress_id
                == StaticIPAddressTable.c.id,
            )
            .join(
                InterfaceTable,
                InterfaceTable.c.id == InterfaceIPAddressTable.c.interface_id,
            )
            .filter(
                StaticIPAddressTable.c.ip
                == IPAddress("fd42:be3f:b08a:3d6c::2"),
                StaticIPAddressTable.c.alloc_type
                == IpAddressType.DISCOVERED.value,
            )
        )

        result = (await db_connection.execute(stmt)).all()

        assert len(result) > 0

    async def test_store_lease_info_expiry(
        self, db_connection: AsyncConnection, fixture: Fixture
    ):
        subnet = await create_test_subnet_entry(fixture, cidr="10.0.0.0/24")
        machine = await create_test_machine_entry(fixture)
        interface = await create_test_interface_entry(fixture, node=machine)
        await create_test_ip_range_entry(
            fixture, subnet=subnet, offset=1, size=5, type="dynamic"
        )
        await create_test_staticipaddress_entry(
            fixture, ip="10.0.0.2", alloc_type=IpAddressType.DISCOVERED.value
        )

        service = await self.create_service(db_connection)
        await service.store_lease_info(
            "expiry",
            "ipv4",
            "10.0.0.2",
            interface.mac_address,
            machine["hostname"],
            int(time.time()),
            30,
        )

        stmt = (
            select(
                StaticIPAddressTable.c.id,
                InterfaceTable.c.id,
            )
            .select_from(
                StaticIPAddressTable,
            )
            .join(
                InterfaceIPAddressTable,
                InterfaceIPAddressTable.c.staticipaddress_id
                == StaticIPAddressTable.c.id,
            )
            .join(
                InterfaceTable,
                InterfaceTable.c.id == InterfaceIPAddressTable.c.interface_id,
            )
            .filter(
                StaticIPAddressTable.c.ip == IPAddress("10.0.0.2"),
                StaticIPAddressTable.c.alloc_type
                == IpAddressType.DISCOVERED.value,
            )
        )

        result = (await db_connection.execute(stmt)).all()

        assert len(result) == 0

    async def test_store_lease_info_release(
        self, db_connection: AsyncConnection, fixture: Fixture
    ):
        subnet = await create_test_subnet_entry(fixture, cidr="10.0.0.0/24")
        machine = await create_test_machine_entry(fixture)
        interface = await create_test_interface_entry(fixture, node=machine)
        await create_test_ip_range_entry(
            fixture, subnet=subnet, offset=1, size=5, type="dynamic"
        )
        await create_test_staticipaddress_entry(
            fixture, ip="10.0.0.2", alloc_type=IpAddressType.DISCOVERED.value
        )

        service = await self.create_service(db_connection)
        await service.store_lease_info(
            "release",
            "ipv4",
            "10.0.0.2",
            interface.mac_address,
            machine["hostname"],
            int(time.time()),
            30,
        )

        stmt = (
            select(
                StaticIPAddressTable.c.id,
                InterfaceTable.c.id,
            )
            .select_from(
                StaticIPAddressTable,
            )
            .join(
                InterfaceIPAddressTable,
                InterfaceIPAddressTable.c.staticipaddress_id
                == StaticIPAddressTable.c.id,
            )
            .join(
                InterfaceTable,
                InterfaceTable.c.id == InterfaceIPAddressTable.c.interface_id,
            )
            .filter(
                StaticIPAddressTable.c.ip == IPAddress("10.0.0.2"),
                StaticIPAddressTable.c.alloc_type
                == IpAddressType.DISCOVERED.value,
            )
        )

        result = (await db_connection.execute(stmt)).all()

        assert len(result) == 0
