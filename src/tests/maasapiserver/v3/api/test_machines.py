from httpx import AsyncClient

from maasapiserver.v3.api.models.responses.machines import MachinesListResponse
from maasapiserver.v3.auth.jwt import UserRole
from maasapiserver.v3.constants import V3_API_PREFIX
from maasapiserver.v3.models.machines import Machine
from tests.fixtures.factories.bmc import create_test_bmc
from tests.fixtures.factories.machines import create_test_machine
from tests.fixtures.factories.node_config import (
    create_test_node_config_entry,
    create_test_numa_node,
    create_test_usb_device,
)
from tests.fixtures.factories.user import create_test_user
from tests.maasapiserver.fixtures.db import Fixture
from tests.maasapiserver.v3.api.base import (
    ApiCommonTests,
    EndpointDetails,
    PaginatedEndpointTestConfig,
)


class TestMachinesApi(ApiCommonTests):
    def get_endpoints_configuration(self) -> list[EndpointDetails]:
        def _assert_machine_in_list(
            machine: Machine, machines_response: MachinesListResponse
        ) -> None:
            machine_response = next(
                filter(
                    lambda machine_response: machine.id == machine_response.id,
                    machines_response.items,
                )
            )
            assert machine.id == machine_response.id
            assert (
                machine.to_response(f"{V3_API_PREFIX}/machines")
                == machine_response
            )

        async def create_pagination_test_resources(
            fixture: Fixture, size: int
        ) -> list[Machine]:
            bmc = await create_test_bmc(fixture)
            user = await create_test_user(fixture)
            created_machines = [
                (
                    await create_test_machine(
                        fixture, description=str(i), bmc=bmc, user=user
                    )
                )
                for i in range(size)
            ]
            return created_machines

        return [
            EndpointDetails(
                method="GET",
                path=f"{V3_API_PREFIX}/machines",
                user_role=UserRole.USER,
                pagination_config=PaginatedEndpointTestConfig[
                    MachinesListResponse
                ](
                    response_type=MachinesListResponse,
                    create_resources_routine=create_pagination_test_resources,
                    assert_routine=_assert_machine_in_list,
                ),
            ),
        ]

    # GET /machines/{system_id}/usb_devices
    async def test_get_usb_devices(
        self, authenticated_user_api_client_v3: AsyncClient, fixture: Fixture
    ) -> None:
        bmc = await create_test_bmc(fixture)
        user = await create_test_user(fixture)
        machine = (
            await create_test_machine(fixture, bmc=bmc, user=user)
        ).dict()
        config = await create_test_node_config_entry(fixture, node=machine)
        numa_node = await create_test_numa_node(fixture, node=machine)
        device = await create_test_usb_device(
            fixture, numa_node=numa_node, config=config
        )

        response = await authenticated_user_api_client_v3.get(
            f"{V3_API_PREFIX}/machines/{machine['system_id']}/usb_devices?size=2"
        )
        assert response.status_code == 200
        assert response.json() == {
            "kind": "MachineHardwareDevicesList",
            "items": [
                {
                    "kind": "MachineHardwareDevice",
                    "id": device.id,
                    "type": device.hardware_type,
                    "vendor_id": device.vendor_id,
                    "product_id": device.product_id,
                    "vendor_name": device.vendor_name,
                    "product_name": device.product_name,
                    "commissioning_driver": device.commissioning_driver,
                    "bus_number": device.bus_number,
                    "device_number": device.device_number,
                    # TODO: FastAPI response_model_exclude_none not working. We need to fix this before making the api public
                    "_embedded": None,
                    "_links": {
                        "self": {
                            "href": f"{V3_API_PREFIX}/machines/{machine['system_id']}/usb_devices/{device.id}"
                        }
                    },
                }
            ],
            "next": None,
        }
