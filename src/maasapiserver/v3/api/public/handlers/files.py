# Copyright 2025 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).
from typing import Union

from fastapi import Depends, Header, Query, Response, status, UploadFile

from maasapiserver.common.api.base import Handler, handler
from maasapiserver.common.api.models.responses.errors import (
    NotFoundBodyResponse,
    NotFoundResponse,
    UnauthorizedBodyResponse,
)
from maasapiserver.v3.api import services
from maasapiserver.v3.api.public.models.responses.files import (
    FileListItemResponse,
    FileListResponse,
    FileResponse,
)
from maasapiserver.v3.auth.base import (
    check_permissions,
    get_authenticated_user,
)
from maasapiserver.v3.constants import V3_API_PREFIX
from maasservicelayer.auth.jwt import UserRole
from maasservicelayer.db.filters import QuerySpec
from maasservicelayer.db.repositories.filestorage import (
    FileStorageClauseFactory,
)
from maasservicelayer.exceptions.catalog import (
    BadRequestException,
    BaseExceptionDetail,
    NotFoundException,
)
from maasservicelayer.exceptions.constants import (
    INVALID_ARGUMENT_VIOLATION_TYPE,
)
from maasservicelayer.models.auth import AuthenticatedUser
from maasservicelayer.services import ServiceCollectionV3


class FilesHandler(Handler):
    """Files API handler."""

    TAGS = ["Files"]

    @handler(
        path="/files",
        methods=["GET"],
        tags=TAGS,
        responses={
            200: {"model": FileListResponse},
            401: {"model": UnauthorizedBodyResponse},
        },
        response_model_exclude_none=True,
        status_code=200,
        dependencies=[
            Depends(check_permissions(required_roles={UserRole.USER}))
        ],
    )
    async def list_files(
        self,
        prefix: str | None = Query(
            description="An optional prefix used to filter files.",
            default=None,
        ),
        authenticated_user: AuthenticatedUser | None = Depends(  # noqa: B008
            get_authenticated_user
        ),
        services: ServiceCollectionV3 = Depends(services),  # noqa: B008
    ) -> FileListResponse:
        assert authenticated_user is not None

        filters = [
            FileStorageClauseFactory.with_owner_id(authenticated_user.id)
        ]
        if prefix:
            filters.append(
                FileStorageClauseFactory.with_filename_prefix(prefix)
            )

        files = await services.filestorage.get_many(
            query=QuerySpec(
                where=FileStorageClauseFactory.and_clauses(filters)
            )
        )

        files = sorted(files, key=lambda file: file.filename)

        return FileListResponse(
            items=[
                FileListItemResponse.from_model(
                    file=file, self_base_hyperlink=f"{V3_API_PREFIX}/files"
                )
                for file in files
            ],
        )

    @handler(
        path="/files:get",
        methods=["GET"],
        tags=TAGS,
        responses={
            200: {"model": FileResponse},
            404: {"model": NotFoundBodyResponse},
        },
        response_model_exclude_none=True,
        status_code=200,
        dependencies=[
            Depends(check_permissions(required_roles={UserRole.USER}))
        ],
    )
    async def get_file(
        self,
        filename: str,
        authenticated_user: AuthenticatedUser | None = Depends(  # noqa: B008
            get_authenticated_user
        ),
        services: ServiceCollectionV3 = Depends(services),  # noqa: B008
    ) -> FileResponse:
        assert authenticated_user is not None
        if not filename:
            raise BadRequestException(
                details=[
                    BaseExceptionDetail(
                        type=INVALID_ARGUMENT_VIOLATION_TYPE,
                        message="Invalid request: No `filename` provided",
                    )
                ]
            )

        file = await services.filestorage.get_one(
            query=QuerySpec(
                where=FileStorageClauseFactory.and_clauses(
                    [
                        FileStorageClauseFactory.with_filename(filename),
                        FileStorageClauseFactory.with_owner_id(
                            authenticated_user.id
                        ),
                    ]
                )
            )
        )
        if not file:
            # In order to fix bug 1123986 we need to distinguish between
            # a 404 returned when the file is not present and a 404 returned
            # when the API endpoint is not present.  We do this by setting
            # a header: "Workaround: bug1123986".
            return NotFoundResponse(
                headers={
                    "Workaround": "bug1123986",
                },
            )  # pyright: ignore[reportReturnType]

        return FileResponse.from_model(
            file=file,
            self_base_hyperlink=f"{V3_API_PREFIX}/files",
        )

    @handler(
        path="/files/{key}",
        methods=["GET"],
        tags=TAGS,
        responses={
            200: {"model": FileResponse},
            404: {"model": NotFoundBodyResponse},
        },
        response_model_exclude_none=True,
        status_code=200,
        dependencies=[
            Depends(check_permissions(required_roles={UserRole.USER}))
        ],
    )
    async def get_file_by_key(
        self,
        key: str,
        authenticated_user: AuthenticatedUser | None = Depends(  # noqa: B008
            get_authenticated_user
        ),
        services: ServiceCollectionV3 = Depends(services),  # noqa: B008
    ) -> FileResponse:
        # Anonymous access to this endpoint is currently required by Juju to
        # retrieve stored files by key in MAAS. However, it can currently
        # access _any_ stored file without authentication regardless of
        # ownership, even though the client they use is authenticated with an
        # API key. We should attempt to resolve this for V3.
        # TODO: Modify handler once discussions with Juju team are resolved.
        assert authenticated_user is not None
        if not key:
            raise BadRequestException(
                details=[
                    BaseExceptionDetail(
                        type=INVALID_ARGUMENT_VIOLATION_TYPE,
                        message="Invalid request: No `key` provided",
                    )
                ]
            )

        file = await services.filestorage.get_one(
            query=QuerySpec(
                where=FileStorageClauseFactory.and_clauses(
                    [
                        FileStorageClauseFactory.with_key(key),
                        FileStorageClauseFactory.with_owner_id(
                            authenticated_user.id
                        ),
                    ]
                )
            )
        )
        if not file:
            raise NotFoundException()

        return FileResponse.from_model(
            file=file,
            self_base_hyperlink=f"{V3_API_PREFIX}/files",
        )

    @handler(
        path="/files",
        methods=["POST"],
        tags=TAGS,
        responses={
            201: {"model": FileResponse},
            401: {"model": UnauthorizedBodyResponse},
        },
        response_model_exclude_none=True,
        status_code=201,
        dependencies=[
            Depends(check_permissions(required_roles={UserRole.USER}))
        ],
    )
    async def create_file(
        self,
        file: UploadFile,
        response: Response,
        filename: str | None = None,
        authenticated_user: AuthenticatedUser | None = Depends(  # noqa: B008
            get_authenticated_user
        ),
        services: ServiceCollectionV3 = Depends(services),  # noqa: B008
    ) -> FileResponse:
        assert authenticated_user is not None

        created_file = await services.filestorage.create_from_upload(
            file, filename, authenticated_user.id
        )

        response.headers["ETag"] = created_file.etag()
        return FileResponse.from_model(
            file=created_file, self_base_hyperlink=f"{V3_API_PREFIX}/files"
        )

    @handler(
        path="/files",
        methods=["DELETE"],
        tags=TAGS,
        responses={
            204: {},
            401: {"model": UnauthorizedBodyResponse},
            404: {"model": NotFoundBodyResponse},
        },
        response_model_exclude_none=True,
        status_code=204,
        dependencies=[
            Depends(check_permissions(required_roles={UserRole.USER}))
        ],
    )
    async def delete_file(
        self,
        filename: str,
        authenticated_user: AuthenticatedUser | None = Depends(  # noqa: B008
            get_authenticated_user
        ),
        etag_if_match: Union[str, None] = Header(
            alias="if-match", default=None
        ),
        services: ServiceCollectionV3 = Depends(services),  # noqa: B008
    ) -> Response:
        assert authenticated_user is not None

        await services.filestorage.delete_one(
            query=QuerySpec(
                where=FileStorageClauseFactory.and_clauses(
                    [
                        FileStorageClauseFactory.with_filename(filename),
                        FileStorageClauseFactory.with_owner_id(
                            authenticated_user.id
                        ),
                    ]
                )
            ),
            etag_if_match=etag_if_match,
        )

        return Response(status_code=status.HTTP_204_NO_CONTENT)
