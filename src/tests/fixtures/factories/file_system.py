from datetime import datetime
from typing import Any

from tests.maasapiserver.fixtures.db import Fixture


async def create_test_file_system_entry(
    fixture: Fixture,
    node: dict[str, Any] | None = None,
    node_config: dict[str, Any] | None = None,
    block_device: dict[str, Any] | None = None,
    cache_set: dict[str, Any] | None = None,
    fs_group: dict[str, Any] | None = None,
    partition: dict[str, Any] | None = None,
    **extra_details: dict[str, Any],
) -> dict[str, Any]:
    created_at = datetime.utcnow().astimezone()
    updated_at = datetime.utcnow().astimezone()
    file_system = {
        "created": created_at,
        "updated": updated_at,
        "uuid": "",
        "fstype": "ext4",
        "label": "root",
        "create_params": "",
        "mount_point": "/",
        "mount_options": "",
        "acquired": False,
    }

    file_system.update(extra_details)

    if node:
        file_system["node_config_id"] = node.get("current_config_id")

    if block_device:
        file_system["block_device_id"] = block_device["id"]
        file_system["node_config_id"] = block_device.get("current_config_id")

    if node_config:
        file_system["node_config_id"] = node_config["id"]

    if cache_set:
        file_system["cache_set_id"] = cache_set["id"]

    if fs_group:
        file_system["filesystem_group_id"] = fs_group["id"]

    if partition:
        file_system["partition_id"] = partition["id"]

    [created_file_system] = await fixture.create(
        "maasserver_filesystem",
        [file_system],
    )
    return created_file_system
