from dataclasses import dataclass

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncConnection
from temporalio import activity, workflow
from temporalio.common import RetryPolicy

from maasapiserver.common.db.tables import InterfaceTable, NodeTable, NodeConfigTable, BlockDeviceTable
from maasserver.enum import NODE_STATUS
from maastemporalworker.workflow.activity import ActivityBase


class NoDiskStatusFound(Exception):
    """
    Exception raised when checking disk status results in no disk(s)
    """
    pass


class NoDeployParamsFound(Exception):
    """
    Exception raised when a dependency for setting deploy params is not found
    """
    pass


@dataclass
class DeployInput:
    system_id: str
    queue: str
    requesting_user_id: int
    osystem: str
    distro_series: str
    hwe_kernel: str
    install_kvm: bool
    register_vmhost: bool
    user_data: str
    enable_hw_sync: bool
    ephemeral_deploy: bool


@dataclass
class DeployNParam:
    """
    Bulk parameters for deploy workflows
    """
    params: list[DeployInput]


@workflow.defn(name="DeployNWorkflow", sandboxed=False)
class DeployNWorkflow:
    """
    Execute multiple deploy workflows
    """

    @workflow.run
    async def run(self, params: DeployNParam) -> None:
        for param in params.params:
            await workflow.execute_child_workflow(
                "deploy",
                param,
                id=f"deploy:{param.system_id}",
                task_queue=param.queue,
                retry_policy=RetryPolicy(maximum_attempts=5),
            )


@dataclass
class SetDeployParamsResult:
    ephemeral_deploy: bool
    register_vmhost: bool
    install_kvm: bool
    install_rackd: bool
    bios_boot_method: str
    osystem: str
    distro_series: str
    architecture: str
    min_hwe_kernel: str
    hwe_kernel: str
    power_state: str
    netboot: bool
    status: int
    previous_status: int
    dynamic: bool
    enable_hw_sync: bool


@dataclass
class CheckDiskStatusInput:
    system_id: str


@dataclass
class CheckDiskStatusResult:
    diskless: bool


@dataclass
class SetBootOrderInput:
    system_id: str
    netboot: bool|None = None


@dataclass
class UpdateNodeStatusInput:
    system_id: str
    status: int


class DeployParamsActivity(ActivityBase):
    async def _register_event(
        self,
        tx: AsyncConnection,
        user_id: int,
        event_type: int,
        action: str | None = "",
        comment: str | None = "",
    ):
        # TODO create event logs
        pass

    @activity.defn(name="set-deploy-params")
    async def set_deploy_params(self, input: DeployInput) -> SetDeployParamsResult:
        async with self.start_transaction() as tx:
            # TODO check user or acquire node

            # TODO validate and fetch appropriate osystem and distro_series values

            # TODO fetch kernel

            # TODO fetch user-data and curtin config

            stmt = (
                NodeTable.update()
                .values(
                    ephemeral_deploy=input.ephemeral_deploy,
                    register_vmhost=input.register_vmhost,
                    install_kvm=input.install_kvm,
                    enable_hw_sync=input.enable_hw_sync,
                    # TODO set osystem, distro_series and hwe_kernel
                )
                .where(NodeTable.c.system_id == input.system_id)
                .returning(
                    NodeTable.c.ephemeral_deploy,
                    NodeTable.c.register_vmhost,
                    NodeTable.c.install_kvm,
                    NodeTable.c.install_rackd,
                    NodeTable.c.bios_boot_method,
                    NodeTable.c.osystem,
                    NodeTable.c.distro_series,
                    NodeTable.c.architecture,
                    NodeTable.c.min_hwe_kernel,
                    NodeTable.c.hwe_kernel,
                    NodeTable.c.power_state,
                    NodeTable.c.netboot,
                    NodeTable.c.status,
                    NodeTable.c.previous_status,
                    NodeTable.c.dynamic,
                    NodeTable.c.enable_hw_sync,
                )
            )
            result = await tx.execute(stmt)
            data = result.one_or_none()
            if not data:
                raise NoDeployParamsFound(
                    f"no node found for system_id: {input.system_id}"
                )
            set_deploy_params = {}
            for i, key in enumerate(result.keys()):
                set_deploy_params[key] = data[i]

            if not result:
                raise NoDeployParamsFound(
                    f"no node found for system_id: {input.system_id}"
                )
            return SetDeployParamsResult(**set_deploy_params)

    @activity.defn(name="check-disk-status")
    async def check_disk_status(self, input: CheckDiskStatusInput) -> CheckDiskStatusResult:
        async with self.start_transaction() as tx:
            stmt = (
                select(func.count(BlockDeviceTable.c.id))
                .select_from(NodeTable)
                .join(
                    NodeConfigTable,
                    NodeTable.c.current_config_id == NodeConfigTable.c.id,
                )
                .join(
                    BlockDeviceTable,
                    NodeConfigTable.c.id == BlockDeviceTable.c.node_config_id,
                )
            )
            result = (await tx.execute(stmt)).one_or_none()
            if not result:
                raise NoDiskStatusFound

            return CheckDiskStatusResult(diskless=result[0] == 0)

    async def _get_boot_order(self, tx: AsyncConnection, input: SetBootOrderInput) -> list[int]:
            interface_stmt = (
                select(
                    InterfaceTable.c.id,
                    NodeTable.c.boot_interface_id,
                ).select_from(NodeTable)
                .join(
                    NodeConfigTable,
                    NodeConfigTable.c.id == NodeTable.c.current_config_id,
                ).join(
                    InterfaceTable,
                    InterfaceTable.c.node_config_id == NodeConfigTable.c.id,
                ).filter(NodeTable.c.system_id == input.system_id)
            )
            iface_result = (await tx.execute(interface_stmt)).all()
            boot_iface_id =  iface_result[0][1]
            ifaces = sorted(
                (
                    iface[0] for iface in iface_result
                ),
                key=lambda iface: (
                    iface != boot_iface_id,
                    iface,
                ),
            )
            
            boot_disk_stmt = select(NodeTable.c.boot_disk_id).select_from(NodeTable).filter(NodeTable.c.system_id == input.system_id)
            boot_disk_id = (await tx.execute(boot_disk_stmt)).one_or_none()

            if boot_disk_id: # TODO check physical block device
                pass
            else:
                pass

            # TODO filter block devices to physical block devices
            block_dvcs_stmt = select(
                BlockDeviceTable.c.id,
            ).select_from(
                NodeTable,
            ).join(
                NodeConfigTable,
                NodeConfigTable.c.id == NodeTable.c.current_config_id,
            ).join(
                BlockDeviceTable,
                BlockDeviceTable.c.node_config_id == NodeConfigTable.c.id,
            ).filter(
                NodeTable.c.system_id == input.system_id
            )
            block_dvcs = sorted(
                (
                    block_dvc[0] for block_dvc in (await tx.execute(block_dvcs_stmt)).all()
                ),
                key=lambda bd: (
                    bd != boot_disk_id,
                    bd,
                ),
            )

            netboot = input.netboot

            if netboot is None:
                node_stmt = select(
                    NodeTable.c.ephemeral_deploy,
                    NodeTable.c.status,
                    NodeTable.c.previous_status,
                ).select_from(
                    NodeTable,
                ).filter(
                    NodeTable.c.system_id==input.system_id,
                )
                node_data = (await tx.execute(node_stmt)).one_or_none()
                ephemeral_deploy, status, previous_status = node_data
                if ephemeral_deploy:
                    netboot = True
                elif status == NODE_STATUS.EXITING_RESCUE_MODE:
                    netboot = previous_status != NODE_STATUS.DEPLOYED
                else:
                    netboot = status != NODE_STATUS.DEPLOYED

            if netboot:
                return ifaces + block_dvcs
            return block_dvcs + ifaces

    @activity.defn(name="set-boot-order")
    async def set_boot_order(self, input: SetBootOrderInput) -> None:
        async with self.start_transaction() as tx:
            power_stmt = (
                select(BMCTable.c.power_type)
                .select_from(NodeTable)
                .join(
                    BMCTable,
                    BMCTable.c.id == NodeTable.c.bmc_id,
                ).filter(
                    NodeTable.c.system_id == system_id,
                )
            )
            [can_set_boot_order] = (await tx.execute(power_stmt)).one_or_none()
            if not can_set_boot_order:
                return
            # TODO use power activity to set boot order

    @activity.defn(name="update-node-status")
    async def update_node_status(self, input: UpdateNodeStatusInput) -> None:
        # TODO set node's status based on result of deploy workflow
        pass
