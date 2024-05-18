import pytest
from sqlalchemy.ext.asyncio import AsyncConnection

from maasapiserver.common.db import Database
from maasapiserver.common.db.tables import NodeTable
from maasserver.enum import NODE_STATUS
from maastemporalworker.workflow.deploy import (
    CheckDiskStatusInput,
    DeployInput,
    DeployParamsActivity,
    NoDeployParamsFound,
    NoDiskStatusFound,
    SetBootOrderInput,
)
from tests.fixtures.factories.block_device import (
    create_test_block_device_entry,
)
from tests.fixtures.factories.bootresource import (
    create_test_bootresource_entry,
    create_test_bootresourcefile_entry,
    create_test_bootresourcefilesync_entry,
    create_test_bootresourceset_entry,
)
from tests.fixtures.factories.interface import create_test_interface_entry
from tests.fixtures.factories.node import (
    create_test_machine_entry,
    create_test_region_controller_entry,
)
from tests.fixtures.factories.user import create_test_user_entry
from tests.maasapiserver.fixtures.db import Fixture


@pytest.mark.asyncio
class TestDeployParamsActivity:
    async def test_set_deploy_params_no_matching_machine(
        self, db: Database, db_connection: AsyncConnection, fixture: Fixture
    ):
        deploy_params_activity = DeployParamsActivity(
            db, connection=db_connection
        )
        try:
            await deploy_params_activity.set_deploy_params(
                DeployInput(
                    system_id="abc",
                    queue="",
                    requesting_user_id=0,
                    osystem="",
                    distro_series="",
                    hwe_kernel="",
                    install_kvm=False,
                    register_vmhost=False,
                    user_data="",
                    enable_hw_sync=True,
                    ephemeral_deploy=True,
                )
            )
        except Exception as e:
            print(e)
            assert isinstance(e, NoDeployParamsFound)

    async def test_set_deploy_params_valid_machine(
        self, db: Database, db_connection: AsyncConnection, fixture: Fixture
    ):
        region_controller = await create_test_region_controller_entry(fixture)
        boot_resource = await create_test_bootresource_entry(
            fixture,
            name="ubuntu/jammy",
            architecture="amd64/ga-22.04",
            kflavor="generic",
            extra={"subarches": "generic,ga-22.04"},
        )
        boot_resource_set = await create_test_bootresourceset_entry(
            fixture, boot_resource
        )
        boot_resource_files = [
            await create_test_bootresourcefile_entry(
                fixture,
                boot_resource_set,
                filename="boot-kernel",
                filetype="boot-kernel",
                extra={"kpackage": "linux-generic"},
            ),
            await create_test_bootresourcefile_entry(
                fixture,
                boot_resource_set,
                filename="squashfs",
                filetype="squashfs",
            ),
            await create_test_bootresourcefile_entry(
                fixture,
                boot_resource_set,
                filename="boot-initrd",
                filetype="boot-initrd",
                extra={"kpackage": "linux-generic"},
            ),
        ]
        [
            await create_test_bootresourcefilesync_entry(
                fixture, region_controller, file
            )
            for file in boot_resource_files
        ]
        machine = await create_test_machine_entry(
            fixture, architecture="amd64/generic"
        )
        user = await create_test_user_entry(fixture)
        deploy_params_activity = DeployParamsActivity(
            db, connection=db_connection
        )
        result = await deploy_params_activity.set_deploy_params(
            DeployInput(
                system_id=machine["system_id"],
                queue="",
                requesting_user_id=user["id"],
                osystem="ubuntu",
                distro_series="jammy",
                hwe_kernel="",
                install_kvm=False,
                register_vmhost=False,
                user_data="",
                enable_hw_sync=False,
                ephemeral_deploy=False,
            )
        )
        for k, v in machine.items():
            if hasattr(result, k):
                if k == "status":
                    # TODO check node status once node acquire is implemented
                    continue
                elif k == "osystem":
                    # TODO check osystem once validation is implemented
                    continue
                elif k == "distro_series":
                    # TODO check distro_series once validation is implemented
                    continue
                elif k == "hwe_kernel":
                    # TODO check hwe_kernel once fetching working kernel is implemented
                    continue
                else:
                    assert getattr(result, k) == v

    async def test_check_disk_status_no_machine(
        self, db: Database, db_connection: AsyncConnection, fixture: Fixture
    ):
        deploy_params_activity = DeployParamsActivity(
            db, connection=db_connection
        )
        try:
            await deploy_params_activity.check_disk_status(
                CheckDiskStatusInput(system_id="abc")
            )
        except Exception as e:
            assert isinstance(e, NoDiskStatusFound)

    async def test_check_disk_status_no_disks(
        self, db: Database, db_connection: AsyncConnection, fixture: Fixture
    ):
        machine = await create_test_machine_entry(fixture)
        deploy_params_activity = DeployParamsActivity(
            db, connection=db_connection
        )
        result = await deploy_params_activity.check_disk_status(
            CheckDiskStatusInput(system_id=machine["system_id"])
        )
        assert result.diskless

    async def test_check_disk_status_machine_with_a_disk(
        self, db: Database, db_connection: AsyncConnection, fixture: Fixture
    ):
        machine = await create_test_machine_entry(fixture)
        await create_test_block_device_entry(fixture, node=machine)
        deploy_params_activity = DeployParamsActivity(
            db, connection=db_connection
        )
        result = await deploy_params_activity.check_disk_status(
            CheckDiskStatusInput(system_id=machine["system_id"])
        )
        assert not result.diskless

    async def test_get_boot_order_netboot_set_true(
        self, db: Database, db_connection: AsyncConnection, fixture: Fixture
    ):
        machine = await create_test_machine_entry(fixture)
        ifaces = [
            await create_test_interface_entry(fixture, node=machine)
            for _ in range(2)
        ]
        block_devices = [
            await create_test_block_device_entry(fixture, node=machine)
            for _ in range(2)
        ]
        boot_stmt = (
            NodeTable.update()
            .values(
                boot_interface_id=ifaces[0]["id"],
                boot_disk_id=block_devices[0]["id"],
            )
            .where(NodeTable.c.system_id == machine["system_id"])
        )
        await db_connection.execute(boot_stmt)

        deploy_params_activity = DeployParamsActivity(
            db, connection=db_connection
        )

        result = await deploy_params_activity._get_boot_order(
            db_connection,
            SetBootOrderInput(system_id=machine["system_id"], netboot=True),
        )
        assert result == [entry["id"] for entry in ifaces + block_devices]

    async def test_get_boot_order_netboot_set_false(
        self, db: Database, db_connection: AsyncConnection, fixture: Fixture
    ):
        machine = await create_test_machine_entry(fixture)
        ifaces = [
            await create_test_interface_entry(fixture, node=machine)
            for _ in range(2)
        ]
        block_devices = [
            await create_test_block_device_entry(fixture, node=machine)
            for _ in range(2)
        ]
        boot_stmt = (
            NodeTable.update()
            .values(
                boot_interface_id=ifaces[0]["id"],
                boot_disk_id=block_devices[0]["id"],
            )
            .where(NodeTable.c.system_id == machine["system_id"])
        )
        await db_connection.execute(boot_stmt)

        deploy_params_activity = DeployParamsActivity(
            db, connection=db_connection
        )

        result = await deploy_params_activity._get_boot_order(
            db_connection,
            SetBootOrderInput(system_id=machine["system_id"], netboot=False),
        )
        assert result == [entry["id"] for entry in block_devices + ifaces]

    async def test_get_boot_order_ephemeral_deploy(
        self, db: Database, db_connection: AsyncConnection, fixture: Fixture
    ):
        machine = await create_test_machine_entry(
            fixture, ephemeral_deploy=True
        )
        ifaces = [
            await create_test_interface_entry(fixture, node=machine)
            for _ in range(2)
        ]
        boot_stmt = (
            NodeTable.update()
            .values(
                boot_interface_id=ifaces[0]["id"],
            )
            .where(NodeTable.c.system_id == machine["system_id"])
        )
        await db_connection.execute(boot_stmt)

        deploy_params_activity = DeployParamsActivity(
            db, connection=db_connection
        )

        result = await deploy_params_activity._get_boot_order(
            db_connection,
            SetBootOrderInput(system_id=machine["system_id"]),
        )
        assert result == [entry["id"] for entry in ifaces]

    async def test_get_boot_order_exiting_rescue_mode(
        self, db: Database, db_connection: AsyncConnection, fixture: Fixture
    ):
        machine = await create_test_machine_entry(
            fixture,
            status=NODE_STATUS.EXITING_RESCUE_MODE,
            previous_status=NODE_STATUS.READY,
        )
        ifaces = [
            await create_test_interface_entry(fixture, node=machine)
            for _ in range(2)
        ]
        block_devices = [
            await create_test_block_device_entry(fixture, node=machine)
            for _ in range(2)
        ]
        boot_stmt = (
            NodeTable.update()
            .values(
                boot_interface_id=ifaces[0]["id"],
                boot_disk_id=block_devices[0]["id"],
            )
            .where(NodeTable.c.system_id == machine["system_id"])
        )
        await db_connection.execute(boot_stmt)

        deploy_params_activity = DeployParamsActivity(
            db, connection=db_connection
        )

        result = await deploy_params_activity._get_boot_order(
            db_connection,
            SetBootOrderInput(system_id=machine["system_id"]),
        )
        assert result == [entry["id"] for entry in ifaces + block_devices]

    async def test_get_boot_order_node_status_ready(
        self, db: Database, db_connection: AsyncConnection, fixture: Fixture
    ):
        machine = await create_test_machine_entry(
            fixture, status=NODE_STATUS.READY
        )
        ifaces = [
            await create_test_interface_entry(fixture, node=machine)
            for _ in range(2)
        ]
        block_devices = [
            await create_test_block_device_entry(fixture, node=machine)
            for _ in range(2)
        ]
        boot_stmt = (
            NodeTable.update()
            .values(
                boot_interface_id=ifaces[0]["id"],
                boot_disk_id=block_devices[0]["id"],
            )
            .where(NodeTable.c.system_id == machine["system_id"])
        )
        await db_connection.execute(boot_stmt)

        deploy_params_activity = DeployParamsActivity(
            db, connection=db_connection
        )

        result = await deploy_params_activity._get_boot_order(
            db_connection,
            SetBootOrderInput(system_id=machine["system_id"]),
        )
        assert result == [entry["id"] for entry in ifaces + block_devices]

    async def test_get_boot_order_node_status_deployed(
        self, db: Database, db_connection: AsyncConnection, fixture: Fixture
    ):
        machine = await create_test_machine_entry(
            fixture, status=NODE_STATUS.DEPLOYED
        )
        ifaces = [
            await create_test_interface_entry(fixture, node=machine)
            for _ in range(2)
        ]
        block_devices = [
            await create_test_block_device_entry(fixture, node=machine)
            for _ in range(2)
        ]
        boot_stmt = (
            NodeTable.update()
            .values(
                boot_interface_id=ifaces[0]["id"],
                boot_disk_id=block_devices[0]["id"],
            )
            .where(NodeTable.c.system_id == machine["system_id"])
        )
        await db_connection.execute(boot_stmt)

        deploy_params_activity = DeployParamsActivity(
            db, connection=db_connection
        )

        result = await deploy_params_activity._get_boot_order(
            db_connection,
            SetBootOrderInput(system_id=machine["system_id"]),
        )
        assert result == [entry["id"] for entry in block_devices + ifaces]
