from typing import Any

from maasservicelayer.models.configurations import DatabaseConfiguration
from tests.maasapiserver.fixtures.db import Fixture


async def create_test_configuration(
    fixture: Fixture, **extra_details: Any
) -> DatabaseConfiguration:
    configuration = {
        "name": "test",
        "value": "test",
    }
    configuration.update(extra_details)

    [created_configuration] = await fixture.create(
        "maasserver_config",
        [configuration],
    )
    return DatabaseConfiguration(**created_configuration)
