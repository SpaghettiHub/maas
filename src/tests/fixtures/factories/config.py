from typing import Any

from maastesting.factory import factory
from tests.maasapiserver.fixtures.db import Fixture


async def create_test_config_entry(
    fixture: Fixture, name: str, **extra_details: dict[str, Any]
) -> dict[str, Any]:
    config = {
        "name": name,
        "value": factory.make_name(),
    }
    config.update(extra_details)

    [created_config] = await fixture.create(
        "maasserver_config",
        [config],
    )
    return created_config
