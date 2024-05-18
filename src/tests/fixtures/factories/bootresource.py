from datetime import datetime
from typing import Any

from maasserver.enum import BOOT_RESOURCE_TYPE
from maastesting.factory import factory
from tests.maasapiserver.fixtures.db import Fixture


async def create_test_bootresource_entry(
    fixture: Fixture, **extra_details: dict[str, Any]
) -> dict[str, Any]:
    created_at = datetime.utcnow().astimezone()
    updated_at = datetime.utcnow().astimezone()
    bootresource = {
        "created": created_at,
        "updated": updated_at,
        "name": factory.make_name(),
        "architecture": "amd64/generic",
        "extra": {},
        "base_image": "",
        "rtype": BOOT_RESOURCE_TYPE.UPLOADED,
        "rolling": False,
    }
    bootresource.update(extra_details)
    [created_bootresource] = await fixture.create(
        "maasserver_bootresource",
        [bootresource],
    )
    return created_bootresource


async def create_test_bootresourceset_entry(
    fixture: Fixture,
    bootresource: dict[str, Any],
    **extra_details: dict[str, Any]
) -> dict[str, Any]:
    created_at = datetime.utcnow().astimezone()
    updated_at = datetime.utcnow().astimezone()
    bootresourceset = {
        "created": created_at,
        "updated": updated_at,
        "resource_id": bootresource["id"],
        "version": factory.make_string(),
        "label": factory.make_string(),
    }
    bootresourceset.update(extra_details)
    [created_bootresourceset] = await fixture.create(
        "maasserver_bootresourceset",
        [bootresourceset],
    )
    return created_bootresourceset


async def create_test_bootresourcefile_entry(
    fixture: Fixture,
    bootresourceset: dict[str, Any],
    **extra_details: dict[str, Any]
) -> dict[str, Any]:
    created_at = datetime.utcnow().astimezone()
    updated_at = datetime.utcnow().astimezone()
    bootresourcefile = {
        "created": created_at,
        "updated": updated_at,
        "filename": factory.make_name(),
        "filetype": "archive.tar.xz",
        "extra": {},
        "sha256": "",
        "size": 0,
        "resource_set_id": bootresourceset["id"],
    }
    bootresourcefile.update(extra_details)
    [created_bootresourcefile] = await fixture.create(
        "maasserver_bootresourcefile",
        bootresourcefile,
    )
    return created_bootresourcefile


async def create_test_bootresourcefilesync_entry(
    fixture: Fixture,
    region_controller: dict[str, Any],
    file: dict[str, Any],
    **extra_details: dict[str, Any]
) -> dict[str, Any]:
    created_at = datetime.utcnow().astimezone()
    updated_at = datetime.utcnow().astimezone()
    bootresourcefilesync = {
        "created": created_at,
        "updated": updated_at,
        "size": 0,
        "file_id": file["id"],
        "region_id": region_controller["id"],
    }
    bootresourcefilesync.update(extra_details)
    [created_bootresourcefilesync] = await fixture.create(
        "maasserver_bootresourcefilesync",
        bootresourcefilesync,
    )
    return created_bootresourcefilesync
