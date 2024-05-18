from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from temporalio import activity

from maasapiserver.common.db.tables import BMCTable, NodeTable
from maastemporalworker.workflow.activity import ActivityBase


class NoPowerParamsFound(Exception):
    """
    An Exception raised in the event no power parameters
    exist for the given system_id
    """
    pass


@dataclass
class GetPowerParamsInput:
    """
    Input data for fetching power parameters of a node
    """

    system_id: str


@dataclass
class GetPowerParamsResult:
    """
    Result data for fetching power parameters of a node
    """

    power_type: int
    power_params: dict[str, Any]


class PowerParamsActivity(ActivityBase):
    """
    Temporal Activities for Power Parameters
    """

    @activity.defn(name="get-power-params")
    async def get_power_params(
        self,
        input: GetPowerParamsInput,
    ) -> GetPowerParamsResult:
        async with self.start_transaction() as tx:
            stmt = (
                select(
                    BMCTable.c.power_type,
                    BMCTable.c.power_parameters,
                )
                .select_from(NodeTable)
                .join(
                    BMCTable,
                    NodeTable.c.bmc_id == BMCTable.c.id,
                )
                .filter(NodeTable.c.system_id == input.system_id)
            )

            result = (await tx.execute(stmt)).one_or_none()
            if not result:
                raise NoPowerParamsFound(
                    f"no power parameters found for system_id: {input.system_id}"
                )

            return GetPowerParamsResult(
                power_type=result[0],
                power_params=result[1],
            )
