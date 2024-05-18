from datetime import datetime
from typing import Any

from sqlalchemy.dialects.postgresql import array

from maastesting.factory import factory
from tests.fixtures.factories.node_config import create_test_node_config_entry
from tests.maasapiserver.fixtures.db import Fixture


async def create_test_block_device_entry(
    fixture: Fixture,
    node: dict[str, Any] | None = None,
    **extra_details: dict[str, Any],
) -> dict[str, Any]:
    created_at = datetime.utcnow().astimezone()
    updated_at = datetime.utcnow().astimezone()
    block_device = {
        "created": created_at,
        "updated": updated_at,
        "name": factory.make_name(),
        "id_path": "/dev/disk/by-id/scsi-SQEMU_QEMU_HARDDISK_lxd_root",
        "size": 4096,
        "block_size": 512,
        "tags": array([]),
    }
    block_device.update(extra_details)

    if node:
        if node.get("current_config_id"):
            block_device["node_config_id"] = node["current_config_id"]
        else:
            config = await create_test_node_config_entry(fixture, node=node)
            block_device["node_config_id"] = config["id"]

    [created_block_device] = await fixture.create(
        "maasserver_blockdevice",
        [block_device],
    )
    return created_block_device
