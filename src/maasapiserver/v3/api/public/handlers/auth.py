# Copyright 2024 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordRequestForm

from maasapiserver.common.api.base import Handler, handler
from maasapiserver.common.api.models.responses.errors import (
    NotFoundBodyResponse,
    UnauthorizedBodyResponse,
)
from maasapiserver.common.utils.http import extract_absolute_uri
from maasapiserver.v3.api import services
from maasapiserver.v3.api.public.models.responses.oauth2 import (
    AccessTokenResponse,
    AuthProviderInfoResponse,
)
from maasapiserver.v3.auth.base import (
    check_permissions,
    get_authenticated_user,
)
from maasservicelayer.auth.jwt import UserRole
from maasservicelayer.exceptions.catalog import (
    BaseExceptionDetail,
    NotFoundException,
)
from maasservicelayer.exceptions.constants import (
    MISSING_PROVIDER_CONFIG_VIOLATION_TYPE,
)
from maasservicelayer.models.auth import AuthenticatedUser
from maasservicelayer.services import ServiceCollectionV3


class AuthHandler(Handler):
    """Auth API handler."""

    TAGS = ["Auth"]

    TOKEN_TYPE = "bearer"

    @handler(
        path="/auth/login",
        methods=["POST"],
        tags=TAGS,
        responses={
            200: {
                "model": AccessTokenResponse,
            },
            401: {"model": UnauthorizedBodyResponse},
        },
        response_model_exclude_none=True,
        status_code=200,
    )
    async def login(
        self,
        request: Request,
        services: ServiceCollectionV3 = Depends(services),  # noqa: B008
        form_data: OAuth2PasswordRequestForm = Depends(),  # noqa: B008
    ) -> AccessTokenResponse:
        if (
            external_auth_info
            := await request.state.services.external_auth.get_external_auth()
        ):
            await request.state.services.external_auth.raise_discharge_required_exception(
                external_auth_info,
                extract_absolute_uri(request),
                request.headers,
            )
        token = await services.auth.login(
            form_data.username, form_data.password
        )
        return AccessTokenResponse(
            token_type=self.TOKEN_TYPE, access_token=token.encoded
        )

    @handler(
        path="/auth/access_token",
        methods=["GET"],
        tags=TAGS,
        responses={
            200: {
                "model": AccessTokenResponse,
            },
            401: {"model": UnauthorizedBodyResponse},
        },
        response_model_exclude_none=True,
        status_code=200,
        dependencies=[
            Depends(check_permissions(required_roles={UserRole.USER}))
        ],
    )
    async def access_token(
        self,
        authenticated_user: AuthenticatedUser | None = Depends(  # noqa: B008
            get_authenticated_user
        ),
        services: ServiceCollectionV3 = Depends(services),  # noqa: B008
    ) -> AccessTokenResponse:
        assert authenticated_user is not None
        token = await services.auth.access_token(authenticated_user)
        return AccessTokenResponse(
            token_type=self.TOKEN_TYPE, access_token=token.encoded
        )

    @handler(
        path="/auth/oauth/initiate",
        methods=["GET"],
        tags=TAGS,
        responses={
            200: {"model": AuthProviderInfoResponse},
            404: {"model": NotFoundBodyResponse},
        },
        status_code=200,
    )
    async def oauth_initiate(
        self,
        services: ServiceCollectionV3 = Depends(services),  # noqa: B008
    ):
        if provider := await services.external_oauth.get_provider():
            return AuthProviderInfoResponse.from_model(provider)

        raise NotFoundException(
            details=[
                BaseExceptionDetail(
                    type=MISSING_PROVIDER_CONFIG_VIOLATION_TYPE,
                    message="No external OAuth provider is configured.",
                )
            ]
        )
