import asyncio
from collections import Counter, defaultdict
from datetime import datetime, timezone
from ipaddress import IPv4Address, IPv6Address
from unittest.mock import AsyncMock, call, Mock

import aiodns
from netaddr import IPAddress, IPNetwork
import pycares
import pytest
from pytest_mock import MockerFixture
from sqlalchemy.ext.asyncio import AsyncConnection
from temporalio import activity
from temporalio.client import Client
from temporalio.testing import ActivityEnvironment, WorkflowEnvironment
from temporalio.worker import Worker

from maascommon.enums.dns import DnsUpdateAction
from maascommon.enums.subnet import RdnsMode
from maascommon.workflows.dns import (
    CONFIGURE_DNS_WORKFLOW_NAME,
    ConfigureDNSParam,
)
from maasservicelayer.db import Database
from maasservicelayer.models.subnets import Subnet
from maasservicelayer.services import CacheForServices
from maastemporalworker.workflow.dns import (
    CHECK_SERIAL_UPDATE_NAME,
    CheckSerialUpdateParam,
    ConfigureDNSWorkflow,
    DNSConfigActivity,
    DNSUpdateResult,
    DYNAMIC_UPDATE_DNS_CONFIGURATION_NAME,
    DynamicUpdateParam,
    FULL_RELOAD_DNS_CONFIGURATION_NAME,
    GET_CHANGES_SINCE_CURRENT_SERIAL_NAME,
    GET_REGION_CONTROLLERS_NAME,
    RegionControllersResult,
    SerialChangesResult,
)
from provisioningserver.dns.config import DynamicDNSUpdate
from tests.fixtures.factories.dnsdata import create_test_dnsdata_entry
from tests.fixtures.factories.dnspublication import (
    create_test_dnspublication_entry,
)
from tests.fixtures.factories.dnsresource import create_test_dnsresource_entry
from tests.fixtures.factories.domain import create_test_domain_entry
from tests.fixtures.factories.interface import create_test_interface_entry
from tests.fixtures.factories.node import (
    create_test_rack_and_region_controller_entry,
    create_test_region_controller_entry,
)
from tests.fixtures.factories.staticipaddress import (
    create_test_staticipaddress_entry,
)
from tests.fixtures.factories.subnet import create_test_subnet_entry
from tests.maasapiserver.fixtures.db import Fixture


@pytest.mark.asyncio
class TestDNSConfigActivity:
    async def test__get_current_serial_from_file(
        self,
        mocker: MockerFixture,
        fixture: Fixture,
        db_connection: AsyncConnection,
        db: Database,
    ) -> None:
        await create_test_domain_entry(fixture)
        mock_file = AsyncMock()
        mock_file.__aiter__.return_value = ["           1000   ; serial"]
        mock_open = mocker.patch("aiofiles.open")
        mock_open.return_value.__aenter__.return_value = mock_file

        services_cache = CacheForServices()

        activities = DNSConfigActivity(
            db,
            services_cache,
            temporal_client=Mock(Client),
            connection=db_connection,
        )

        async with activities.start_transaction() as svc:
            serial = await activities._get_current_serial_from_file(svc)

        assert serial == 1000

    async def test_get_changes_since_current_serial(
        self,
        mocker: MockerFixture,
        fixture: Fixture,
        db_connection: AsyncConnection,
        db: Database,
    ) -> None:
        env = ActivityEnvironment()

        domain = await create_test_domain_entry(fixture)
        await create_test_subnet_entry(
            fixture, cidr="10.0.0.0/24", allow_dns=True
        )
        mock_file = AsyncMock()
        mock_file.__aiter__.return_value = ["           1   ; serial"]
        mock_open = mocker.patch("aiofiles.open")
        mock_open.return_value.__aenter__.return_value = mock_file
        [
            await create_test_dnspublication_entry(
                fixture,
                serial=i + 2,
                update=f"INSERT {domain.name} rec{i + 1} A 30 10.0.0.{i + 1}",
            )
            for i in range(5)
        ]

        services_cache = CacheForServices()

        activities = DNSConfigActivity(
            db,
            services_cache,
            temporal_client=Mock(Client),
            connection=db_connection,
        )

        _, result = await env.run(
            activities.get_changes_since_current_serial,
        )

        # the dnspublication fixtures
        assert result.updates == [
            DynamicDNSUpdate(
                operation=DnsUpdateAction.INSERT,
                zone=domain.name,
                name=f"rec{i + 1}",
                ttl=30,
                rectype="A",
                answer=f"10.0.0.{i + 1}",
                subnet="10.0.0.0/24",
                rev_zone="0.0.10.in-addr.arpa",
                ip=f"10.0.0.{i + 1}",
            )
            for i in range(5)
        ]

    async def test_get_changes_since_last_serial_handles_no_current_serial(
        self,
        mocker: MockerFixture,
        fixture: Fixture,
        db_connection: AsyncConnection,
        db: Database,
    ) -> None:
        env = ActivityEnvironment()

        await create_test_domain_entry(fixture)
        mock_file = AsyncMock()
        mock_file.__aiter__.return_value = [""]
        mock_open = mocker.patch("aiofiles.open")
        mock_open.return_value.__aenter__.return_value = mock_file

        services_cache = CacheForServices()

        activities = DNSConfigActivity(
            db,
            services_cache,
            temporal_client=Mock(Client),
            connection=db_connection,
        )

        serial, result = await env.run(
            activities.get_changes_since_current_serial,
        )

        assert serial == 0
        assert result.force_reload

    async def test__dnspublication_to_dnsupdate(
        self, fixture: Fixture, db: Database, db_connection: AsyncConnection
    ) -> None:
        domain = await create_test_domain_entry(fixture, name="example.com")
        await create_test_subnet_entry(
            fixture, cidr="10.0.0.0/24", allow_dns=True
        )
        iface = await create_test_interface_entry(fixture)
        await create_test_dnsresource_entry(
            fixture, name="test", domain=domain
        )
        testcases = [
            (
                await create_test_dnspublication_entry(
                    fixture, update="RELOAD"
                ),
                [
                    DynamicDNSUpdate(
                        operation=DnsUpdateAction.RELOAD,
                        zone="",
                        name="",
                        rectype="",
                    )
                ],
            ),
            (
                await create_test_dnspublication_entry(
                    fixture, update="INSERT example.com test A 30 10.0.0.1"
                ),
                [
                    DynamicDNSUpdate(
                        operation=DnsUpdateAction.INSERT,
                        zone="example.com",
                        name="test",
                        rectype="A",
                        ttl=30,
                        answer="10.0.0.1",
                        ip="10.0.0.1",
                        subnet="10.0.0.0/24",
                        rev_zone="0.0.10.in-addr.arpa",
                    )
                ],
            ),
            (
                await create_test_dnspublication_entry(
                    fixture, update="UPDATE example.com test A 30 10.0.0.1"
                ),
                [
                    DynamicDNSUpdate(
                        operation=DnsUpdateAction.DELETE,
                        zone="example.com",
                        name="test",
                        rectype="A",
                        ttl=None,
                        answer="10.0.0.1",
                        ip="10.0.0.1",
                        subnet="10.0.0.0/24",
                        rev_zone="0.0.10.in-addr.arpa",
                    ),
                    DynamicDNSUpdate(
                        operation=DnsUpdateAction.INSERT,
                        zone="example.com",
                        name="test",
                        rectype="A",
                        ttl=30,
                        answer="10.0.0.1",
                        ip="10.0.0.1",
                        subnet="10.0.0.0/24",
                        rev_zone="0.0.10.in-addr.arpa",
                    ),
                ],
            ),
            (
                await create_test_dnspublication_entry(
                    fixture, update="DELETE example.com test A 30 10.0.0.1"
                ),
                [
                    DynamicDNSUpdate(
                        operation=DnsUpdateAction.DELETE,
                        zone="example.com",
                        name="test",
                        rectype="A",
                        ttl=30,
                        answer="10.0.0.1",
                        ip="10.0.0.1",
                        subnet="10.0.0.0/24",
                        rev_zone="0.0.10.in-addr.arpa",
                    )
                ],
            ),
            (
                await create_test_dnspublication_entry(
                    fixture, update="DELETE example.com test A"
                ),
                [
                    DynamicDNSUpdate(
                        operation=DnsUpdateAction.DELETE,
                        zone="example.com",
                        name="test",
                        rectype="A",
                        ttl=30,
                    )
                ],
            ),
            (
                await create_test_dnspublication_entry(
                    fixture, update="DELETE-IP example.com test A 10.0.0.1"
                ),
                [
                    DynamicDNSUpdate(
                        operation=DnsUpdateAction.DELETE,
                        zone="example.com",
                        name="test",
                        rectype="A",
                    ),
                    DynamicDNSUpdate(
                        operation=DnsUpdateAction.DELETE,
                        zone="example.com",
                        name="test",
                        rectype="AAAA",
                    ),
                ],
            ),
            (
                await create_test_dnspublication_entry(
                    fixture,
                    update=f"DELETE-IFACE-IP example.com test A {iface.id}",
                ),
                [
                    DynamicDNSUpdate(
                        operation=DnsUpdateAction.DELETE,
                        zone="example.com",
                        name="test",
                        rectype="A",
                    ),
                    DynamicDNSUpdate(
                        operation=DnsUpdateAction.DELETE,
                        zone="example.com",
                        name="test",
                        rectype="AAAA",
                    ),
                ],
            ),
        ]

        services_cache = CacheForServices()

        activities = DNSConfigActivity(
            db,
            services_cache,
            temporal_client=Mock(Client),
            connection=db_connection,
        )

        async with activities.start_transaction() as svc:
            for testcase in testcases:
                result = await activities._dnspublication_to_dnsupdate(
                    svc, testcase[0], 30
                )
                assert result == testcase[1]

    async def test_get_region_controllers(
        self, fixture: Fixture, db_connection: AsyncConnection, db: Database
    ) -> None:
        env = ActivityEnvironment()

        region_controllers = [
            await create_test_region_controller_entry(fixture)
            for _ in range(3)
        ]

        services_cache = CacheForServices()

        activities = DNSConfigActivity(
            db,
            services_cache,
            temporal_client=Mock(Client),
            connection=db_connection,
        )

        result = await env.run(
            activities.get_region_controllers,
        )

        assert [
            r["system_id"] for r in region_controllers
        ] == result.region_controller_system_ids

    async def test__get_dns_ip_addresses(
        self, fixture: Fixture, db_connection: AsyncConnection, db: Database
    ) -> None:
        subnets = [
            await create_test_subnet_entry(fixture, allow_dns=True)
            for _ in range(3)
        ]
        sips = [
            [
                (
                    await create_test_staticipaddress_entry(
                        fixture, subnet=subnet
                    )
                )[0]
                for subnet in subnets
            ]
            for _ in range(3)
        ]
        [
            (await create_test_staticipaddress_entry(fixture, subnet=subnet))[
                0
            ]
            for subnet in subnets
        ]  # additional IPs that should be excluded
        controllers = [
            await create_test_rack_and_region_controller_entry(fixture)
            for _ in range(3)
        ]
        [
            await create_test_interface_entry(
                fixture, node=controllers[i], ips=[sip]
            )
            for i, ctrlr_sips in enumerate(sips)
            for sip in ctrlr_sips
        ]

        services_cache = CacheForServices()

        activities = DNSConfigActivity(
            db,
            services_cache,
            connection=db_connection,
            temporal_client=Mock(Client),
        )

        async with activities.start_transaction() as svc:
            ips = await activities._get_dns_ip_addresses(svc)
            assert set([str(ip) for ip in ips]) == {
                str(ip["ip"]) for ctrlr_sips in sips for ip in ctrlr_sips
            }

    async def test__get_ttl(
        self, fixture: Fixture, db_connection: AsyncConnection, db: Database
    ) -> None:
        domain = await create_test_domain_entry(fixture)
        dnsresource = await create_test_dnsresource_entry(
            fixture, domain=domain
        )

        services_cache = CacheForServices()

        activities = DNSConfigActivity(
            db,
            services_cache,
            temporal_client=Mock(Client),
            connection=db_connection,
        )

        ttl = activities._get_ttl(30, domain, dnsresource)

        assert ttl == domain.ttl

    async def test__get_fwd_records(
        self, fixture: Fixture, db_connection: AsyncConnection, db: Database
    ) -> None:
        domains = [await create_test_domain_entry(fixture) for _ in range(3)]
        subnet1 = await create_test_subnet_entry(fixture, allow_dns=True)
        subnet2 = await create_test_subnet_entry(fixture, allow_dns=True)
        sips = [
            (await create_test_staticipaddress_entry(fixture, subnet=subnet1))[
                0
            ]
            for _ in range(3)
        ]
        ctrlr_sips = [
            (
                await create_test_staticipaddress_entry(
                    fixture, subnet=subnet1 if i % 2 == 0 else subnet2
                )
            )[0]
            for i in range(3)
        ]
        controller = await create_test_rack_and_region_controller_entry(
            fixture
        )
        await create_test_interface_entry(
            fixture, node=controller, ips=ctrlr_sips
        )
        dnsresources = [
            await create_test_dnsresource_entry(fixture, domain=d, ip=sips[i])
            for d in domains
            for i in range(3)
        ]
        dnsdata = [
            await create_test_dnsdata_entry(fixture, dnsresource=d)
            for d in dnsresources
        ]

        services_cache = CacheForServices()

        activities = DNSConfigActivity(
            db,
            services_cache,
            temporal_client=Mock(Client),
            connection=db_connection,
        )

        async with activities.start_transaction() as svc:
            result = await activities._get_fwd_records(svc, domains, 30)

        expected = defaultdict(lambda: defaultdict(list))
        for domain in domains:
            for ip in ctrlr_sips:
                if isinstance(ip["ip"], IPv4Address):
                    expected[domain.name][("@", "A")].append(
                        (str(ip["ip"]), domain.ttl)
                    )
                if isinstance(ip["ip"], IPv6Address):
                    expected[domain.name][("@", "AAAA")].append(
                        (str(ip["ip"]), domain.ttl)
                    )

            for i, dnsrr in enumerate(dnsresources):
                if dnsrr.domain_id == domain.id:
                    ip = sips[i % 3]

                    if isinstance(ip["ip"], IPv4Address):
                        expected[domain.name][(dnsrr.name, "A")].append(
                            (
                                str(ip["ip"]),
                                activities._get_ttl(30, domain, dnsrr),
                            )
                        )

                    if isinstance(ip["ip"], IPv6Address):
                        expected[domain.name][(dnsrr.name, "AAAA")].append(
                            (
                                str(ip["ip"]),
                                activities._get_ttl(30, domain, dnsrr),
                            )
                        )
                    for dd in dnsdata:
                        if dd.dnsresource_id == dnsrr.id:
                            expected[domain.name][
                                (dnsrr.name, dd.rrtype)
                            ].append(
                                (
                                    dd.rrdata,
                                    activities._get_ttl(30, domain, dnsrr, dd),
                                )
                            )

        for k, v in expected.items():
            for k2, v2 in v.items():
                assert v2 == result[k][k2]

    async def test__split_large_subnet(
        self, fixture: Fixture, db_connection: AsyncConnection, db: Database
    ) -> None:
        network = IPNetwork("10.0.0.0/22")

        services_cache = CacheForServices()

        activities = DNSConfigActivity(
            db,
            services_cache,
            temporal_client=Mock(Client),
            connection=db_connection,
        )

        split = activities._split_large_subnet(network)

        assert set(split) == {
            IPNetwork("10.0.0.0/24"),
            IPNetwork("10.0.1.0/24"),
            IPNetwork("10.0.2.0/24"),
            IPNetwork("10.0.3.0/24"),
        }

    async def test__generate_glue_networks(
        self, fixture: Fixture, db_connection: AsyncConnection, db: Database
    ) -> None:
        subnets = [
            await create_test_subnet_entry(fixture, cidr=f"10.0.{i}.0/28")
            for i in range(3)
        ]

        services_cache = CacheForServices()

        activities = DNSConfigActivity(
            db,
            services_cache,
            temporal_client=Mock(Client),
            connection=db_connection,
        )

        result = activities._generate_glue_networks(
            [Subnet(**subnet) for subnet in subnets]
        )

        assert result == {
            IPAddress("10.0.0.0"): {IPNetwork("10.0.0.0/28")},
            IPAddress("10.0.1.0"): {IPNetwork("10.0.1.0/28")},
            IPAddress("10.0.2.0"): {IPNetwork("10.0.2.0/28")},
        }

    async def test__find_glue_network(
        self, fixture: Fixture, db_connection: AsyncConnection, db: Database
    ) -> None:
        network = IPNetwork("10.0.0.0/24")
        glue_nets = {
            IPAddress("10.0.0.0"): {IPNetwork("10.0.0.0/28")},
            IPAddress("10.0.1.0"): {IPNetwork("10.0.1.0/28")},
        }

        services_cache = CacheForServices()

        activities = DNSConfigActivity(
            db,
            services_cache,
            temporal_client=Mock(Client),
            connection=db_connection,
        )

        glue = activities._find_glue_network(network, glue_nets)

        assert glue == {IPNetwork("10.0.0.0/28")}

    async def test__get_rev_zone_name(
        self, db_connection: AsyncConnection, db: Database
    ) -> None:
        in_vals = [IPNetwork("10.2.1.0/24"), IPNetwork("10.2.1.0/28")]
        out_vals = ["1.2.10.in-addr.arpa", "0-28.1.2.10.in-addr.arpa"]

        services_cache = CacheForServices()

        activities = DNSConfigActivity(
            db,
            services_cache,
            temporal_client=Mock(Client),
            connection=db_connection,
        )

        for idx, i in enumerate(in_vals):
            result = activities._get_rev_zone_name(i)
            assert result == out_vals[idx]

    async def test__get_rev_records(
        self, fixture: Fixture, db_connection: AsyncConnection, db: Database
    ) -> None:
        domains = [await create_test_domain_entry(fixture) for _ in range(3)]
        subnets = [await create_test_subnet_entry(fixture) for _ in range(3)]
        sips = [
            (
                await create_test_staticipaddress_entry(
                    fixture, subnet=subnets[i]
                )
            )[0]
            for i in range(3)
        ]
        dnsresources = [
            await create_test_dnsresource_entry(fixture, domain=d, ip=sips[i])
            for d in domains
            for i in range(3)
        ]
        [
            await create_test_dnsdata_entry(fixture, dnsresource=d)
            for d in dnsresources
        ]

        services_cache = CacheForServices()

        activities = DNSConfigActivity(
            db,
            services_cache,
            temporal_client=Mock(Client),
            connection=db_connection,
        )

        async with activities.start_transaction() as svc:
            fwd_recs = await activities._get_fwd_records(svc, domains, 30)
            rev_recs = await activities._get_rev_records(
                svc, [Subnet(**subnet) for subnet in subnets], fwd_recs
            )

        for _, recs in rev_recs.items():
            for name, answers in recs.items():
                assert name[0] in [
                    IPAddress(str(sip["ip"])).reverse_dns for sip in sips
                ]
                assert len(answers) == 3

    async def test__rndc_cmd(
        self,
        mocker: MockerFixture,
        db_connection: AsyncConnection,
        db: Database,
    ) -> None:
        mock_proc = AsyncMock()
        mock_proc.wait.return_value = 0
        mock_exec = mocker.patch("asyncio.create_subprocess_exec")
        mock_exec.return_value = mock_proc

        services_cache = CacheForServices()

        activities = DNSConfigActivity(
            db,
            services_cache,
            temporal_client=Mock(Client),
            connection=db_connection,
        )

        mock_get_rndc_config_path = mocker.patch.object(
            activities, "_get_rndc_conf_path"
        )
        mock_get_rndc_config_path.return_value = "/tmp/rndc.conf"

        await activities._rndc_cmd(["freeze"])

        mock_exec.assert_called_once_with(
            "rndc", "-c", "/tmp/rndc.conf", "freeze"
        )

    async def test__freeze(
        self,
        mocker: MockerFixture,
        db_connection: AsyncConnection,
        db: Database,
    ) -> None:
        mock_proc = AsyncMock()
        mock_proc.wait.return_value = 0
        mock_exec = mocker.patch("asyncio.create_subprocess_exec")
        mock_exec.return_value = mock_proc

        services_cache = CacheForServices()

        activities = DNSConfigActivity(
            db,
            services_cache,
            temporal_client=Mock(Client),
            connection=db_connection,
        )

        mock_get_rndc_config_path = mocker.patch.object(
            activities, "_get_rndc_conf_path"
        )
        mock_get_rndc_config_path.return_value = "/tmp/rndc.conf"

        async with activities._freeze():
            pass

        assert (
            call("rndc", "-c", "/tmp/rndc.conf", "freeze")
            in mock_exec.mock_calls
        )
        assert (
            call("rndc", "-c", "/tmp/rndc.conf", "thaw")
            in mock_exec.mock_calls
        )

    async def test__write_bind_files(
        self,
        mocker: MockerFixture,
        db_connection: AsyncConnection,
        db: Database,
    ) -> None:
        mock_proc = AsyncMock()
        mock_proc.wait.return_value = 0
        mock_exec = mocker.patch("asyncio.create_subprocess_exec")
        mock_exec.return_value = mock_proc

        mock_file = AsyncMock()
        mock_open = mocker.patch("aiofiles.open")
        mock_open.return_value.__aenter__.return_value = mock_file
        mock_rename = mocker.patch("aiofiles.os.rename")

        services_cache = CacheForServices()

        activities = DNSConfigActivity(
            db,
            services_cache,
            temporal_client=Mock(Client),
            connection=db_connection,
        )

        mock_get_zone_config_path = mocker.patch(
            "maastemporalworker.workflow.dns.get_zone_config_path"
        )
        mock_get_zone_config_path.return_value = "/tmp/named.conf.maas"
        mock_get_zone_file_path = mocker.patch(
            "maastemporalworker.workflow.dns.get_zone_file_path"
        )
        mock_get_zone_file_path.return_value = "/tmp/zone.test.com"
        mock_get_rndc_config_path = mocker.patch.object(
            activities, "_get_rndc_conf_path"
        )
        mock_get_rndc_config_path.return_value = "/tmp/rndc.conf"
        mock_get_named_rndc_config_path = mocker.patch.object(
            activities, "_get_named_rndc_conf_path"
        )
        mock_get_named_rndc_config_path.return_value = "/tmp/rndc.conf"
        mock_get_nsupdate_key_path = mocker.patch.object(
            activities, "_get_nsupdate_keys_path"
        )
        mock_get_nsupdate_key_path.return_value = "/tmp/key.conf.maas"

        modified = datetime.now(timezone.utc)

        await activities._write_bind_files(
            {"test.com": {("a", "A"): [("10.0.0.1", 30)]}},
            1000,
            zone_ttls={"test.com": 30},
            modified=modified,
        )

        assert (
            call("rndc", "-c", "/tmp/rndc.conf", "freeze")
            in mock_exec.mock_calls
        )
        assert (
            call("rndc", "-c", "/tmp/rndc.conf", "thaw")
            in mock_exec.mock_calls
        )

        expected_conf = """include "/tmp/rndc.conf";
include "/tmp/key.conf.maas";

# Authoritative Zone declarations.
zone "test.com" {
    type master;
    # Disable forwarding for authoritive zones, lp:2118833
    forwarders { };
    file "/tmp/zone.test.com";
    allow-update {
        key maas.;
    };
};

# Forwarded Zone declarations.

# Access control for recursive queries.  See named.conf.options.inside.maas
# for the directives used on this ACL.
acl "trusted" {
    localnets;
    localhost;
};
"""
        expected_zone_file = f"""; Zone file modified: {modified}.
$TTL 30
@   IN    SOA test.com. nobody.example.com. (
              1000 ; serial
              600 ; Refresh
              1800 ; Retry
              604800 ; Expire
              30 ; NXTTL
              )

@   30 IN NS .
a 30 IN A 10.0.0.1
"""

        print(mock_file.write.mock_calls)

        assert call(expected_conf) in mock_file.write.mock_calls
        assert call(expected_zone_file) in mock_file.write.mock_calls

        assert (
            call("/tmp/named.conf.maas.tmp", "/tmp/named.conf.maas")
            in mock_rename.mock_calls
        )
        assert (
            call("/tmp/zone.test.com.tmp", "/tmp/zone.test.com")
            in mock_rename.mock_calls
        )

    async def test_full_reload_dns_configuration(
        self,
        mocker: MockerFixture,
        fixture: Fixture,
        db: Database,
        db_connection: AsyncConnection,
    ) -> None:
        env = ActivityEnvironment()

        mock_proc = AsyncMock()
        mock_proc.wait.return_value = 0
        mock_exec = mocker.patch("asyncio.create_subprocess_exec")
        mock_exec.return_value = mock_proc

        mock_file = AsyncMock()
        mock_open = mocker.patch("aiofiles.open")
        mock_open.return_value.__aenter__.return_value = mock_file
        mocker.patch("aiofiles.os.rename")

        services_cache = CacheForServices()

        activities = DNSConfigActivity(
            db,
            services_cache,
            temporal_client=Mock(Client),
            connection=db_connection,
        )

        mock_get_zone_config_path = mocker.patch(
            "maastemporalworker.workflow.dns.get_zone_config_path"
        )
        mock_get_zone_config_path.return_value = "/tmp/named.conf.maas"
        mock_get_zone_file_path = mocker.patch(
            "maastemporalworker.workflow.dns.get_zone_file_path"
        )
        mock_get_zone_file_path.return_value = "/tmp/zone.test.com"
        mock_get_rndc_config_path = mocker.patch.object(
            activities, "_get_rndc_conf_path"
        )
        mock_get_rndc_config_path.return_value = "/tmp/rndc.conf"
        mock_get_nsupdate_key_path = mocker.patch.object(
            activities, "_get_nsupdate_keys_path"
        )
        mock_get_nsupdate_key_path.return_value = "/tmp/key.conf.maas"

        domain = await create_test_domain_entry(fixture)
        subnet = await create_test_subnet_entry(
            fixture,
            rdns_mode=RdnsMode.ENABLED,
            cidr="10.0.0.0/24",
            allow_dns=True,
        )
        sip = (
            await create_test_staticipaddress_entry(fixture, subnet=subnet)
        )[0]
        await create_test_dnsresource_entry(fixture, domain=domain, ip=sip)

        result = await env.run(
            activities.full_reload_dns_configuration,
        )

        async with activities.start_transaction() as svc:
            latest_serial = await svc.dnspublications.get_latest_serial()

        assert len(mock_file.write.mock_calls) == 5
        assert result.serial == latest_serial

    async def test_dynamic_update_dns_configuration(
        self,
        mocker: MockerFixture,
        db: Database,
        db_connection: AsyncConnection,
    ) -> None:
        env = ActivityEnvironment()

        mock_exec = mocker.patch("asyncio.create_subprocess_exec")

        services_cache = CacheForServices()

        activities = DNSConfigActivity(
            db,
            services_cache,
            temporal_client=Mock(Client),
            connection=db_connection,
        )

        result = await env.run(
            activities.dynamic_update_dns_configuration,
            DynamicUpdateParam(
                new_serial=1000,
                updates=[
                    DynamicDNSUpdate(
                        operation=DnsUpdateAction.INSERT,
                        zone="example.com",
                        name="test",
                        rectype="A",
                        ttl=30,
                        answer="10.0.0.1",
                    ),
                ],
            ),
        )

        mock_exec.assert_called_once()

        assert result.serial == 1000

    async def test_check_serial_update(
        self,
        mocker: MockerFixture,
        db: Database,
        db_connection: AsyncConnection,
    ) -> None:
        env = ActivityEnvironment()

        services_cache = CacheForServices()

        activities = DNSConfigActivity(
            db,
            services_cache,
            temporal_client=Mock(Client),
            connection=db_connection,
        )

        mock_query = asyncio.Future()
        mock_answer = AsyncMock(pycares.ares_query_soa_result)
        mock_answer.nsname = ("example.com",)
        mock_answer.hostmaster = ("nobody.example.com",)
        mock_answer.serial = 1000
        mock_answer.refresh = 600
        mock_answer.retry = 600
        mock_answer.expires = 10000
        mock_answer.minttl = 30
        mock_answer.ttl = 30
        mock_query.set_result(mock_answer)
        mock_resolver = AsyncMock(aiodns.DNSResolver)
        mock_resolver.query.return_value = mock_query
        mock_get_resolver = mocker.patch.object(activities, "_get_resolver")
        mock_get_resolver.return_value = mock_resolver

        await env.run(
            activities.check_serial_update,
            CheckSerialUpdateParam(serial=1000),
        )

        mock_resolver.query.assert_called_once_with("maas", "SOA")


@pytest.mark.asyncio
class TestDNSConfigWorkflow:
    async def test_dns_config_workflow_full_reload(
        self, mocker: MockerFixture
    ):
        # TODO create DNSPublications, Domains and DNSResources for update

        mocker.patch(
            "maastemporalworker.workflow.dns.get_task_queue_for_update"
        ).return_value = "region"

        calls = Counter()

        @activity.defn(name=GET_CHANGES_SINCE_CURRENT_SERIAL_NAME)
        async def get_changes_since_current_serial() -> (
            int,
            SerialChangesResult | None,
        ):
            calls.update([GET_CHANGES_SINCE_CURRENT_SERIAL_NAME])
            return 100, None

        @activity.defn(name=GET_REGION_CONTROLLERS_NAME)
        async def get_region_controllers() -> RegionControllersResult:
            calls.update([GET_REGION_CONTROLLERS_NAME])
            return RegionControllersResult(
                region_controller_system_ids=["abc"]
            )

        @activity.defn(name=FULL_RELOAD_DNS_CONFIGURATION_NAME)
        async def full_reload_dns_configuration() -> DNSUpdateResult:
            calls.update([FULL_RELOAD_DNS_CONFIGURATION_NAME])
            return DNSUpdateResult(serial=1)

        @activity.defn(name=DYNAMIC_UPDATE_DNS_CONFIGURATION_NAME)
        async def dynamic_update_dns_configuration(
            updates: DynamicUpdateParam,
        ) -> DNSUpdateResult:
            calls.update([DYNAMIC_UPDATE_DNS_CONFIGURATION_NAME])
            return DNSUpdateResult(serial=1)

        @activity.defn(name=CHECK_SERIAL_UPDATE_NAME)
        async def check_serial_update(serial: CheckSerialUpdateParam) -> None:
            calls.update([CHECK_SERIAL_UPDATE_NAME])

        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="region",
                workflows=[ConfigureDNSWorkflow],
                activities=[
                    get_changes_since_current_serial,
                    get_region_controllers,
                    full_reload_dns_configuration,
                    dynamic_update_dns_configuration,
                    check_serial_update,
                ],
            ) as worker:
                await env.client.execute_workflow(
                    CONFIGURE_DNS_WORKFLOW_NAME,
                    ConfigureDNSParam(need_full_reload=True),
                    id="configure-dns",
                    task_queue=worker.task_queue,
                )

                assert calls[GET_CHANGES_SINCE_CURRENT_SERIAL_NAME] == 0
                assert calls[GET_REGION_CONTROLLERS_NAME] == 1
                assert calls[FULL_RELOAD_DNS_CONFIGURATION_NAME] == 1
                assert calls[DYNAMIC_UPDATE_DNS_CONFIGURATION_NAME] == 0
                assert calls[CHECK_SERIAL_UPDATE_NAME] == 1

    async def test_dns_config_workflow_dynamic_update(
        self, mocker: MockerFixture
    ) -> None:
        # TODO create DNSPublications, Domains and DNSResources for update

        mocker.patch(
            "maastemporalworker.workflow.dns.get_task_queue_for_update"
        ).return_value = "region"

        calls = Counter()

        @activity.defn(name=GET_CHANGES_SINCE_CURRENT_SERIAL_NAME)
        async def get_changes_since_current_serial() -> (
            int,
            SerialChangesResult | None,
        ):
            calls.update([GET_CHANGES_SINCE_CURRENT_SERIAL_NAME])
            return 100, SerialChangesResult(
                updates=[
                    DynamicDNSUpdate(
                        operation=DnsUpdateAction.UPDATE,
                        name="",
                        zone="",
                        rectype="",
                    )
                ],
                force_reload=False,
            )

        @activity.defn(name=GET_REGION_CONTROLLERS_NAME)
        async def get_region_controllers() -> RegionControllersResult:
            calls.update([GET_REGION_CONTROLLERS_NAME])
            return RegionControllersResult(
                region_controller_system_ids=["abc"]
            )

        @activity.defn(name=FULL_RELOAD_DNS_CONFIGURATION_NAME)
        async def full_reload_dns_configuration() -> DNSUpdateResult:
            calls.update([FULL_RELOAD_DNS_CONFIGURATION_NAME])
            return DNSUpdateResult(serial=1)

        @activity.defn(name=DYNAMIC_UPDATE_DNS_CONFIGURATION_NAME)
        async def dynamic_update_dns_configuration(
            updates: DynamicUpdateParam,
        ) -> DNSUpdateResult:
            calls.update([DYNAMIC_UPDATE_DNS_CONFIGURATION_NAME])
            return DNSUpdateResult(serial=1)

        @activity.defn(name=CHECK_SERIAL_UPDATE_NAME)
        async def check_serial_update(serial: CheckSerialUpdateParam) -> None:
            calls.update([CHECK_SERIAL_UPDATE_NAME])

        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="region",
                workflows=[ConfigureDNSWorkflow],
                activities=[
                    get_changes_since_current_serial,
                    get_region_controllers,
                    full_reload_dns_configuration,
                    dynamic_update_dns_configuration,
                    check_serial_update,
                ],
            ) as worker:
                await env.client.execute_workflow(
                    CONFIGURE_DNS_WORKFLOW_NAME,
                    ConfigureDNSParam(need_full_reload=False),
                    id="configure-dns",
                    task_queue=worker.task_queue,
                )

                assert calls[GET_CHANGES_SINCE_CURRENT_SERIAL_NAME] == 1
                assert calls[GET_REGION_CONTROLLERS_NAME] == 1
                assert calls[FULL_RELOAD_DNS_CONFIGURATION_NAME] == 0
                assert calls[DYNAMIC_UPDATE_DNS_CONFIGURATION_NAME] == 1
                assert calls[CHECK_SERIAL_UPDATE_NAME] == 1

    async def test_dns_config_workflow_full_reloads_with_no_current_serial(
        self, mocker: MockerFixture
    ):
        mocker.patch(
            "maastemporalworker.workflow.dns.get_task_queue_for_update"
        ).return_value = "region"

        calls = Counter()

        @activity.defn(name=GET_CHANGES_SINCE_CURRENT_SERIAL_NAME)
        async def get_changes_since_current_serial() -> (
            int,
            SerialChangesResult | None,
        ):
            calls.update([GET_CHANGES_SINCE_CURRENT_SERIAL_NAME])
            return -1, SerialChangesResult(
                updates=[],
                force_reload=True,
            )

        @activity.defn(name=GET_REGION_CONTROLLERS_NAME)
        async def get_region_controllers() -> RegionControllersResult:
            calls.update([GET_REGION_CONTROLLERS_NAME])
            return RegionControllersResult(
                region_controller_system_ids=["abc"]
            )

        @activity.defn(name=FULL_RELOAD_DNS_CONFIGURATION_NAME)
        async def full_reload_dns_configuration() -> DNSUpdateResult:
            calls.update([FULL_RELOAD_DNS_CONFIGURATION_NAME])
            return DNSUpdateResult(serial=1)

        @activity.defn(name=DYNAMIC_UPDATE_DNS_CONFIGURATION_NAME)
        async def dynamic_update_dns_configuration(
            updates: DynamicUpdateParam,
        ) -> DNSUpdateResult:
            calls.update([DYNAMIC_UPDATE_DNS_CONFIGURATION_NAME])
            return DNSUpdateResult(serial=1)

        @activity.defn(name=CHECK_SERIAL_UPDATE_NAME)
        async def check_serial_update(serial: CheckSerialUpdateParam) -> None:
            calls.update([CHECK_SERIAL_UPDATE_NAME])

        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="region",
                workflows=[ConfigureDNSWorkflow],
                activities=[
                    get_changes_since_current_serial,
                    get_region_controllers,
                    full_reload_dns_configuration,
                    dynamic_update_dns_configuration,
                    check_serial_update,
                ],
            ) as worker:
                await env.client.execute_workflow(
                    CONFIGURE_DNS_WORKFLOW_NAME,
                    ConfigureDNSParam(need_full_reload=False),
                    id="configure-dns",
                    task_queue=worker.task_queue,
                )

        assert calls[GET_CHANGES_SINCE_CURRENT_SERIAL_NAME] == 1
        assert calls[GET_REGION_CONTROLLERS_NAME] == 1
        assert calls[FULL_RELOAD_DNS_CONFIGURATION_NAME] == 1
        assert calls[DYNAMIC_UPDATE_DNS_CONFIGURATION_NAME] == 0
        assert calls[CHECK_SERIAL_UPDATE_NAME] == 1
