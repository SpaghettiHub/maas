# Copyright 2025 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).
from datetime import datetime
from typing import List, Optional, Self

from pydantic import BaseModel

from maasapiserver.v3.api.public.models.responses.base import (
    BaseHal,
    BaseHref,
    HalResponse,
)
from maascommon.enums.boot_resources import BootResourceType
from maasservicelayer.models.bootresources import BootResource


class BootResourceResponse(HalResponse[BaseHal]):
    kind = "BootResource"

    id: int
    name: str
    architecture: str
    base_image: str
    rtype: BootResourceType
    extra: dict
    rolling: bool
    kflavor: Optional[str]
    bootloader_type: Optional[str]
    alias: Optional[str]
    last_deployed: Optional[datetime]

    @classmethod
    def from_model(
        cls, boot_resource: BootResource, self_base_hyperlink: str
    ) -> Self:
        return cls(
            id=boot_resource.id,
            name=boot_resource.name,
            architecture=boot_resource.architecture,
            base_image=boot_resource.base_image,
            rtype=boot_resource.rtype,
            extra=boot_resource.extra,
            rolling=boot_resource.rolling,
            kflavor=boot_resource.kflavor,
            bootloader_type=boot_resource.bootloader_type,
            alias=boot_resource.alias,
            last_deployed=boot_resource.last_deployed,
            hal_links=BaseHal(  # pyright: ignore [reportCallIssue]
                self=BaseHref(
                    href=f"{self_base_hyperlink.rstrip('/')}/{boot_resource.id}"
                )
            ),
        )


class BootResourceListResponse(BaseModel):
    kind = "BootResourceList"

    items: List[BootResourceResponse]
