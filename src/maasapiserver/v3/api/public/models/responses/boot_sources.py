# Copyright 2025 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from typing import Optional, Self

from pydantic import BaseModel

from maasapiserver.v3.api.public.models.responses.base import (
    BaseHal,
    BaseHref,
    HalResponse,
    PaginatedResponse,
)
from maasservicelayer.models.bootsourcecache import BootSourceCache
from maasservicelayer.models.bootsources import (
    BootSource,
    SourceAvailableImage,
)


class BootSourceResponse(HalResponse[BaseHal]):
    kind = "BootSource"
    id: int
    url: str
    keyring_filename: Optional[str]
    keyring_data: Optional[str]
    priority: int
    skip_keyring_verification: bool

    @classmethod
    def from_model(
        cls, boot_source: BootSource, self_base_hyperlink: str
    ) -> Self:
        keyring_data = boot_source.keyring_data or b""
        keyring_data = keyring_data.decode("utf-8")
        return cls(
            id=boot_source.id,
            url=boot_source.url,
            keyring_filename=boot_source.keyring_filename,
            keyring_data=keyring_data,
            priority=boot_source.priority,
            skip_keyring_verification=boot_source.skip_keyring_verification,
            hal_links=BaseHal(  # pyright: ignore [reportCallIssue]
                self=BaseHref(
                    href=f"{self_base_hyperlink.rstrip('/')}/{boot_source.id}"
                )
            ),
        )


class BootSourcesListResponse(PaginatedResponse[BootSourceResponse]):
    kind = "BootSourcesList"


class BaseSourceAvailableImageResponse(BaseModel):
    os: str
    release: str
    architecture: str


class SourceAvailableImageResponse(BaseSourceAvailableImageResponse):
    kind = "SourceAvailableImage"
    release_title: str

    @classmethod
    def from_model(
        cls,
        source_image: SourceAvailableImage,
    ) -> Self:
        return cls(
            os=source_image.os,
            release=source_image.release,
            release_title=source_image.release_title,
            architecture=source_image.architecture,
        )


class SourceAvailableImageListResponse(BaseModel):
    kind = "SourceAvailableImageList"
    items: list[SourceAvailableImageResponse]


class BootSourceAvailableImageResponse(BaseSourceAvailableImageResponse):
    kind = "BootSourceAvailableImage"

    @classmethod
    def from_model(
        cls,
        boot_source_cache: BootSourceCache,
    ) -> Self:
        return cls(
            os=boot_source_cache.os,
            release=boot_source_cache.release,
            architecture=boot_source_cache.arch,
        )


class BootSourceAvailableImageListResponse(
    PaginatedResponse[BootSourceAvailableImageResponse]
):
    kind = "BootSourceAvailableImageList"


class UISourceAvailableImageResponse(BaseSourceAvailableImageResponse):
    kind = "UISourceAvailableImage"
    source_id: Optional[int]
    source_name: Optional[str]

    @classmethod
    def from_model(
        cls,
        boot_source: BootSource,
        boot_source_cache: BootSourceCache,
    ) -> Self:
        return cls(
            os=boot_source_cache.os,
            release=boot_source_cache.release,
            architecture=boot_source_cache.arch,
            source_id=boot_source.id,
            source_name=boot_source.url,
        )


class UISourceAvailableImageListResponse(BaseModel):
    kind = "UISourceAvailableImageList"
    items: list[UISourceAvailableImageResponse]
