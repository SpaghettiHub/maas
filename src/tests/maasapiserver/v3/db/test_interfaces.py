from math import ceil

import pytest
from sqlalchemy.ext.asyncio import AsyncConnection

from maasapiserver.v3.api.models.requests.query import PaginationParams
from maasapiserver.v3.db.interfaces import InterfaceRepository
from maasapiserver.v3.models.base import ListResult
from maasapiserver.v3.models.interfaces import Interface
from maasserver.enum import IPADDRESS_TYPE
from tests.fixtures.factories.bmc import create_test_bmc
from tests.fixtures.factories.interface import (
    create_test_interface,
    create_test_interface_entry,
)
from tests.fixtures.factories.machines import create_test_machine
from tests.fixtures.factories.node_config import create_test_node_config_entry
from tests.fixtures.factories.staticipaddress import (
    create_test_staticipaddress_entry,
)
from tests.fixtures.factories.subnet import create_test_subnet_entry
from tests.fixtures.factories.user import create_test_user
from tests.fixtures.factories.vlan import create_test_vlan_entry
from tests.maasapiserver.fixtures.db import Fixture


def _assert_interfaces_match_without_links(
    interface1: Interface, interface2: Interface
) -> None:
    assert interface1.id == interface2.id
    interface1.links = []
    interface2.links = []
    assert (
        interface1 == interface2
    ), f"{interface1} does not match {interface2}!"


@pytest.mark.usefixtures("ensuremaasdb")
@pytest.mark.asyncio
class TestInterfaceRepository:
    @pytest.mark.parametrize("page_size", range(1, 12))
    @pytest.mark.parametrize(
        "alloc_type",
        ["AUTO", "STICKY", "USER_RESERVED"],
    )
    async def test_list(
        self,
        page_size: int,
        alloc_type: int,
        db_connection: AsyncConnection,
        fixture: Fixture,
    ) -> None:
        def _assert_interface_in_list(
            interface: Interface, interfaces_response: ListResult[Interface]
        ) -> None:
            interface_response = next(
                filter(
                    lambda interface_response: interface.id
                    == interface_response.id,
                    interfaces_response.items,
                )
            )
            assert interface.id == interface_response.id
            assert (
                interface == interface_response
            ), f"{interface} does not match {interface_response}!"

        bmc = await create_test_bmc(fixture)
        user = await create_test_user(fixture)
        machine = (
            await create_test_machine(fixture, bmc=bmc, user=user)
        ).dict()
        config = await create_test_node_config_entry(fixture, node=machine)
        machine["current_config_id"] = config["id"]

        interface_count = 4
        interfaces_repository = InterfaceRepository(db_connection)
        created_interfaces = [
            (
                await create_test_interface(
                    fixture,
                    name=str(i),
                    node=machine,
                    ip_count=4,
                    alloc_type=getattr(IPADDRESS_TYPE, alloc_type),
                )
            )
            for i in range(0, interface_count)
        ][::-1]

        total_pages = ceil(interface_count / page_size)
        for page in range(1, total_pages + 1):
            interfaces_result = await interfaces_repository.list(
                node_id=machine["id"],
                pagination_params=PaginationParams(size=page_size, page=page),
            )
            assert interfaces_result.total == interface_count
            assert total_pages == ceil(interfaces_result.total / page_size)

            expected_length = len(interfaces_result.items)
            if page == total_pages:  # last page may have fewer elements
                page_length = min(
                    interface_count,
                    page_size
                    - ((total_pages * page_size) % interfaces_result.total),
                )
            else:
                page_length = page_size
            assert (
                expected_length == page_length
            ), f"page {page} has length {page_length}? expected {expected_length}"

            for interface in created_interfaces[
                ((page - 1) * page_size) : ((page * page_size))
            ]:
                _assert_interface_in_list(interface, interfaces_result)

    async def test_list_links_empty_if_only_discovered_type(
        self, db_connection: AsyncConnection, fixture: Fixture
    ) -> None:
        # Discovered links are not returned from the database when listing
        # all the links on an interface, so this should be empty

        def _assert_interface_in_list(
            interface: Interface, interfaces_response: ListResult[Interface]
        ) -> None:
            interface_response = next(
                filter(
                    lambda interface_response: interface.id
                    == interface_response.id,
                    interfaces_response.items,
                )
            )
            # we create, but don't return any links
            assert interface.links
            assert interface_response.links == []

            _assert_interfaces_match_without_links(
                interface, interface_response
            )

        bmc = await create_test_bmc(fixture)
        user = await create_test_user(fixture)
        machine = (
            await create_test_machine(fixture, bmc=bmc, user=user)
        ).dict()
        config = await create_test_node_config_entry(fixture, node=machine)
        machine["current_config_id"] = config["id"]

        interface_count = 4
        interfaces_repository = InterfaceRepository(db_connection)
        created_interfaces = [
            (
                await create_test_interface(
                    fixture,
                    name=str(i),
                    node=machine,
                    ip_count=4,
                    alloc_type=IPADDRESS_TYPE.DISCOVERED,
                )
            )
            for i in range(0, interface_count)
        ][::-1]

        interfaces_result = await interfaces_repository.list(
            node_id=machine["id"],
            pagination_params=PaginationParams(size=interface_count, page=1),
        )

        for interface in created_interfaces:
            _assert_interface_in_list(interface, interfaces_result)

    async def test_list_interfaces_use_discovered_ip_for_dhcp_links(
        self, db_connection: AsyncConnection, fixture: Fixture
    ) -> None:
        # A dhcp link gets it ip address from discovered links on the same subnet
        # if we have some, their ip address should match the first discovered

        def _assert_interface_in_list(
            interface: Interface, interfaces_response: ListResult[Interface]
        ) -> None:
            interface_response = next(
                filter(
                    lambda interface_response: interface.id
                    == interface_response.id,
                    interfaces_response.items,
                )
            )
            assert interface.id == interface_response.id

            # each dhcp ip should be followed its relevant discovered ip
            created_links = sorted(interface.links, key=lambda link: link.id)
            response_links = sorted(
                interface_response.links, key=lambda link: link.id
            )

            for (
                created_discovery,
                created_dhcp,
                response_discovery,
                response_dhcp,
            ) in zip(
                created_links[::2],
                created_links[1::2],
                response_links[::2],
                response_links[1::2],
            ):
                assert created_dhcp == response_dhcp
                assert created_discovery == response_discovery

                assert created_dhcp.ip_type == IPADDRESS_TYPE.DHCP
                assert created_dhcp.ip_address is None, created_dhcp

                assert created_discovery.ip_type == IPADDRESS_TYPE.DISCOVERED
                assert (
                    created_discovery.ip_address is not None
                ), created_discovery

            _assert_interfaces_match_without_links(
                interface, interface_response
            )

        bmc = await create_test_bmc(fixture)
        user = await create_test_user(fixture)
        machine = (
            await create_test_machine(fixture, bmc=bmc, user=user)
        ).dict()
        config = await create_test_node_config_entry(fixture, node=machine)
        machine["current_config_id"] = config["id"]

        ip_count = 4
        interface_count = 4
        interfaces_repository = InterfaceRepository(db_connection)

        created_interfaces = []
        for i in range(0, interface_count):
            vlan = await create_test_vlan_entry(fixture)
            subnet = await create_test_subnet_entry(
                fixture, vlan_id=vlan["id"]
            )

            ips = []
            for _ in range(ip_count):
                ips.extend(
                    await create_test_staticipaddress_entry(
                        fixture=fixture,
                        subnet=subnet,
                        alloc_type=IPADDRESS_TYPE.DHCP,
                    )
                )
            this_interface = await create_test_interface_entry(
                fixture=fixture,
                name=str(i),
                node=machine,
                ips=ips[::-1],
                vlan=vlan,
            )
            created_interfaces.insert(0, this_interface)

        interfaces_result = await interfaces_repository.list(
            node_id=machine["id"],
            pagination_params=PaginationParams(size=interface_count, page=1),
        )

        for interface in created_interfaces:
            _assert_interface_in_list(interface, interfaces_result)
