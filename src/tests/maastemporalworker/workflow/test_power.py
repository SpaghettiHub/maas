import pytest
from sqlalchemy.ext.asyncio import AsyncConnection

from maasapiserver.common.db import Database
from maastemporalworker.workflow.power import (
    GetPowerParamsInput,
    NoPowerParamsFound,
    PowerParamsActivity,
)
from tests.fixtures.factories.bmc import create_test_bmc_entry
from tests.fixtures.factories.node import create_test_machine_entry
from tests.maasapiserver.fixtures.db import Fixture


@pytest.mark.asyncio
class TestPowerParamsActivity:
    async def test_get_power_params_no_matching_machine(
        self, db: Database, db_connection: AsyncConnection, fixture: Fixture
    ) -> None:
        power_params_activities = PowerParamsActivity(
            db,
            connection=db_connection,
        )

        try:
            await power_params_activities.get_power_params(
                GetPowerParamsInput(system_id="abc")
            )
        except Exception as e:
            assert isinstance(e, NoPowerParamsFound)

    async def test_get_power_params_missing_bmc(
        self, db: Database, db_connection: AsyncConnection, fixture: Fixture
    ) -> None:
        machine = await create_test_machine_entry(fixture)
        power_params_activities = PowerParamsActivity(
            db, connection=db_connection
        )
        try:
            await power_params_activities.get_power_params(
                GetPowerParamsInput(system_id=machine["system_id"])
            )
        except Exception as e:
            assert isinstance(e, NoPowerParamsFound)

    async def test_get_power_params_valid_data(
        self, db: Database, db_connection: AsyncConnection, fixture: Fixture
    ) -> None:
        bmc = await create_test_bmc_entry(fixture)
        machine = await create_test_machine_entry(fixture, bmc_id=bmc["id"])
        power_params_activities = PowerParamsActivity(
            db, connection=db_connection
        )
        result = await power_params_activities.get_power_params(
            GetPowerParamsInput(system_id=machine["system_id"])
        )
        assert result.power_type == bmc["power_type"]
        assert result.power_params == bmc["power_parameters"]
