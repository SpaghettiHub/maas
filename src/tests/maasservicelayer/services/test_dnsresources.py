import pytest
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncConnection

from maascommon.enums.ipaddress import IpAddressType
from maasservicelayer.db.tables import (
    DNSResourceIPAddressTable,
    DNSResourceTable,
    StaticIPAddressTable,
)
from maasservicelayer.models.staticipaddress import StaticIPAddress
from maasservicelayer.services.dnsresources import DNSResourcesService
from maasservicelayer.services.domains import DomainsService
from tests.fixtures.factories.dnsresource import create_test_dnsresource_entry
from tests.fixtures.factories.domain import create_test_domain_entry
from tests.fixtures.factories.staticipaddress import (
    create_test_staticipaddress_entry,
)
from tests.fixtures.factories.subnet import create_test_subnet_entry
from tests.maasapiserver.fixtures.db import Fixture


@pytest.mark.asyncio
class TestDNSResourcesService:
    def _create_service(
        self, db_connection: AsyncConnection
    ) -> DNSResourcesService:
        return DNSResourcesService(
            db_connection,
            DomainsService(
                db_connection,
            ),
        )

    async def test_get_or_create_create(
        self, db_connection: AsyncConnection, fixture: Fixture
    ) -> None:
        domain = await create_test_domain_entry(fixture)

        dnsresources_service = self._create_service(db_connection)

        stmt = (
            select(DNSResourceTable)
            .select_from(DNSResourceTable)
            .where(
                DNSResourceTable.c.name == "test_name",
                DNSResourceTable.c.domain_id == domain.id,
            )
        )

        initial = (await db_connection.execute(stmt)).one_or_none()

        assert initial is None

        dnsrr, created = await dnsresources_service.get_or_create(
            name="test_name", domain_id=domain.id
        )

        result = (await db_connection.execute(stmt)).one_or_none()

        assert result is not None
        assert result._asdict()["id"] == dnsrr.id
        assert created

    async def test_get_or_create_get(
        self, db_connection: AsyncConnection, fixture: Fixture
    ) -> None:
        domain = await create_test_domain_entry(fixture)
        dnsresource = await create_test_dnsresource_entry(
            fixture, name="test_name", domain=domain
        )

        dnsresources_service = self._create_service(db_connection)

        result, created = await dnsresources_service.get_or_create(
            name="test_name", domain_id=domain.id
        )

        assert result is not None
        assert dnsresource.id == result.id
        assert created is False

    async def test_release_dynamic_hostname_no_remaining_ips(
        self, db_connection: AsyncConnection, fixture: Fixture
    ) -> None:
        domain_service = DomainsService(db_connection)
        domain = await domain_service.get_default_domain()
        subnet = await create_test_subnet_entry(fixture)
        sip = (
            await create_test_staticipaddress_entry(
                fixture,
                subnet=subnet,
                alloc_type=IpAddressType.DISCOVERED.value,
            )
        )[0]
        dnsresource = await create_test_dnsresource_entry(fixture, domain, sip)

        dnsresources_service = self._create_service(db_connection)

        stmt = (
            select(StaticIPAddressTable)
            .select_from(DNSResourceTable)
            .join(
                DNSResourceIPAddressTable,
                DNSResourceIPAddressTable.c.dnsresource_id
                == DNSResourceTable.c.id,
            )
            .join(
                StaticIPAddressTable,
                StaticIPAddressTable.c.id
                == DNSResourceIPAddressTable.c.staticipaddress_id,
            )
            .filter(DNSResourceTable.c.id == dnsresource.id)
        )

        initial = (await db_connection.execute(stmt)).one()

        assert initial._asdict()["id"] == sip["id"]

        await dnsresources_service.release_dynamic_hostname(
            StaticIPAddress(**sip)
        )

        result = (await db_connection.execute(stmt)).one_or_none()

        assert result is None

    async def test_release_dynamic_hostname_remaining_ips(
        self, db_connection: AsyncConnection, fixture: Fixture
    ) -> None:
        domain_service = DomainsService(db_connection)
        domain = await domain_service.get_default_domain()
        subnet = await create_test_subnet_entry(fixture)
        sip1 = (
            await create_test_staticipaddress_entry(
                fixture,
                subnet=subnet,
                alloc_type=IpAddressType.DISCOVERED.value,
            )
        )[0]
        sip2 = (
            await create_test_staticipaddress_entry(
                fixture,
                subnet=subnet,
                alloc_type=IpAddressType.DISCOVERED.value,
            )
        )[0]
        dnsresource = await create_test_dnsresource_entry(
            fixture, domain, sip1
        )

        second_link_stmt = insert(DNSResourceIPAddressTable).values(
            dnsresource_id=dnsresource.id, staticipaddress_id=sip2["id"]
        )

        await db_connection.execute(second_link_stmt)

        dnsresources_service = self._create_service(db_connection)

        stmt = (
            select(StaticIPAddressTable)
            .select_from(DNSResourceTable)
            .join(
                DNSResourceIPAddressTable,
                DNSResourceIPAddressTable.c.dnsresource_id
                == DNSResourceTable.c.id,
            )
            .join(
                StaticIPAddressTable,
                StaticIPAddressTable.c.id
                == DNSResourceIPAddressTable.c.staticipaddress_id,
            )
            .filter(DNSResourceTable.c.id == dnsresource.id)
        )

        initial = (await db_connection.execute(stmt)).first()

        assert initial._asdict()["id"] == sip1["id"]

        await dnsresources_service.release_dynamic_hostname(
            StaticIPAddress(**sip1)
        )

        result = (await db_connection.execute(stmt)).one_or_none()

        assert result._asdict()["id"] != sip1["id"]

    async def test_update_dynamic_hostname(
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

        dnsresources_service = self._create_service(db_connection)

        stmt = (
            select(StaticIPAddressTable)
            .select_from(DNSResourceTable)
            .join(
                DNSResourceIPAddressTable,
                DNSResourceIPAddressTable.c.dnsresource_id
                == DNSResourceTable.c.id,
            )
            .join(
                StaticIPAddressTable,
                StaticIPAddressTable.c.id
                == DNSResourceIPAddressTable.c.staticipaddress_id,
            )
            .filter(DNSResourceTable.c.name == "test-name")
        )

        initial = (await db_connection.execute(stmt)).one_or_none()

        assert initial is None

        await dnsresources_service.update_dynamic_hostname(
            StaticIPAddress(**sip), "test_name"
        )

        result = (await db_connection.execute(stmt)).one_or_none()

        assert result._asdict()["id"] == sip["id"]
