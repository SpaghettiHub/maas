from maasapiserver.v3.api.models.responses.interfaces import (
    InterfaceListResponse,
)
from maasapiserver.v3.auth.jwt import UserRole
from maasapiserver.v3.models.interfaces import Interface
from tests.fixtures.factories.bmc import create_test_bmc
from tests.fixtures.factories.interface import create_test_interface
from tests.fixtures.factories.machines import create_test_machine
from tests.fixtures.factories.node_config import create_test_node_config_entry
from tests.fixtures.factories.user import create_test_user
from tests.maasapiserver.fixtures.db import Fixture
from tests.maasapiserver.v3.api.base import (
    ApiCommonTests,
    EndpointDetails,
    PaginatedEndpointTestConfig,
)


class TestInterfaceApi(ApiCommonTests):
    def get_endpoints_configuration(self) -> list[EndpointDetails]:
        def _assert_interface_in_list(
            interface: Interface, interfaces_response: InterfaceListResponse
        ) -> None:
            interface_response = next(
                filter(
                    lambda interface_response: interface.id
                    == interface_response.id,
                    interfaces_response.items,
                )
            )
            assert interface.id == interface_response.id

            # We have no way of knowing the node id to construct the path
            iface = interface.to_response(
                str(interface_response.hal_links.self.href).rsplit("/", 1)[0]
            )
            assert (
                iface == interface_response
            ), f"{iface} does not match {interface_response}!"

        async def create_pagination_test_resources(
            fixture: Fixture, size: int
        ) -> list[Interface]:
            bmc = await create_test_bmc(fixture)
            user = await create_test_user(fixture)
            machine = (
                await create_test_machine(fixture, bmc=bmc, user=user)
            ).dict()
            config = await create_test_node_config_entry(fixture, node=machine)
            machine["current_config_id"] = config["id"]

            return [
                (
                    await create_test_interface(
                        fixture,
                        description=str(i),
                        node=machine,
                        ip_count=4,
                    )
                )
                for i in range(0, size)
            ]

        # We cannot access the node ID outside of the setup function
        return [
            EndpointDetails(
                method="GET",
                path="/api/v3/machines/{id}/interfaces",
                user_role=UserRole.USER,
                pagination_config=PaginatedEndpointTestConfig(
                    response_type=InterfaceListResponse,
                    assert_routine=_assert_interface_in_list,
                    create_resources_routine=create_pagination_test_resources,
                ),
            ),
        ]
