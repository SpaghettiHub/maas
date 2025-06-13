# Copyright 2025 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from fastapi import Depends

from maasapiserver.common.api.base import Handler, handler
from maasapiserver.v3.api import services
from maasapiserver.v3.api.public.models.requests.boot_sources import (
    BootSourcesRequest,
)
from maasapiserver.v3.api.public.models.responses.boot_sources import (
    BootSourceResponse,
    BootSourcesListResponse,
)
from maasapiserver.v3.auth.base import check_permissions
from maasapiserver.v3.constants import V3_API_PREFIX
from maasservicelayer.auth.jwt import UserRole
from maasservicelayer.services import ServiceCollectionV3


class BootSourcesHandler(Handler):
    """BootSources API handler."""

    TAGS = ["BootSources"]

    @handler(
        path="/boot_sources:fetch",
        methods=["POST"],
        tags=TAGS,
        responses={
            200: {
                "model": BootSourcesListResponse,
            },
        },
        status_code=200,
        response_model_exclude_none=True,
        dependencies=[
            Depends(check_permissions(required_roles={UserRole.USER}))
        ],
    )
    async def list_boot_sources(
        self,
        request: BootSourcesRequest,
        services: ServiceCollectionV3 = Depends(services),  # noqa: B008
    ) -> BootSourcesListResponse:
        # TODO: Change fetch return type to ListResult[...] ?
        boot_source_mapping = await services.boot_sources.fetch(
            request.url,
            keyring=request.keyring,
            user_agent=request.user_agent,
            validate_products=request.validate_products,
        )
        # The fetch method isn't paginated, so we return all items
        # in a single response.
        return BootSourcesListResponse(
            items=[
                BootSourceResponse.from_model(
                    boot_source,
                    self_base_hyperlink=f"{V3_API_PREFIX}/boot_sources",
                )
                for boot_source in boot_source_mapping.items()
            ],
            total=len(boot_source_mapping),
            next=None,
        )
