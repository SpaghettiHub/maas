# Copyright 2025 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from datetime import datetime
from typing import Optional, Tuple

from maasapiserver.v3.api.public.models.responses.base import (
    BaseHal,
    BaseHref,
    HalResponse,
    PaginatedResponse,
)
from maasservicelayer.utils.images.helpers import ImageSpec


class BootSourceResponse(HalResponse[BaseHal]):
    kind = "BootSource"

    os: str
    arch: str
    subarch: str
    kflavor: str
    release: str
    label: Optional[str]

    content_id: str
    product_name: str
    version_name: str
    path: str

    subarches: Optional[str]
    bootloader_type: Optional[str]
    release_title: Optional[str]
    release_codename: Optional[str]
    support_eol: Optional[datetime]

    @classmethod
    def from_model(
        cls,
        boot_source: Tuple[ImageSpec, dict[str, str]],
        self_base_hyperlink: str,
    ) -> "BootSourceResponse":
        image_spec, metadata = boot_source
        parsed_support_eol = None
        if "support_eol" in metadata:
            parsed_support_eol = datetime.strptime(
                metadata["support_eol"], "%Y-%m-%d"
            )

        return cls(
            os=image_spec.os,
            arch=image_spec.arch,
            subarch=image_spec.subarch,
            kflavor=image_spec.kflavor,
            release=image_spec.release,
            label=metadata.get("label"),
            content_id=metadata.get("content_id"),
            product_name=metadata.get("product_name"),
            version_name=metadata.get("version_name"),
            path=metadata.get("path"),
            subarches=metadata.get("subarches"),
            bootloader_type=metadata.get("bootloader_type"),
            release_title=metadata.get("release_title"),
            release_codename=metadata.get("release_codename"),
            support_eol=parsed_support_eol,
            # TODO: This is a placeholder for now.
            # TODO: If using path, url encode it.
            hal_links=BaseHal(
                self=BaseHref(
                    href=f"{self_base_hyperlink}/?url={metadata['path']}"
                )
            ),
        )


class BootSourcesListResponse(PaginatedResponse[BootSourceResponse]):
    kind = "BootSourcesList"
