#  Copyright 2025 Canonical Ltd.  This software is licensed under the
#  GNU Affero General Public License version 3 (see the file LICENSE).
from uuid import uuid4

from fastapi import UploadFile

from maasservicelayer.builders.filestorage import FileStorageBuilder
from maasservicelayer.context import Context
from maasservicelayer.db.repositories.filestorage import FileStorageRepository
from maasservicelayer.exceptions.catalog import (
    BadRequestException,
    BaseExceptionDetail,
)
from maasservicelayer.exceptions.constants import (
    MISSING_FILE_FILENAME_VIOLATION_TYPE,
)
from maasservicelayer.models.filestorage import FileStorage
from maasservicelayer.services.base import BaseService, ServiceCache


class FileStorageService(
    BaseService[FileStorage, FileStorageRepository, FileStorageBuilder]
):
    def __init__(
        self,
        context: Context,
        repository: FileStorageRepository,
        cache: ServiceCache | None = None,
    ):
        super().__init__(context, repository, cache)

    async def create(self, builder):
        raise NotImplementedError("Use `create_from_upload` instead.")

    async def create_from_upload(
        self,
        file: UploadFile,
        filename: str | None = None,
        owner_id: int | None = None,
    ) -> FileStorage:
        data = await file.read()
        file_name_to_create = file.filename if not filename else filename  # pyright: ignore[reportArgumentType]
        if not file_name_to_create or file_name_to_create == "":
            raise BadRequestException(
                details=[
                    BaseExceptionDetail(
                        type=MISSING_FILE_FILENAME_VIOLATION_TYPE,
                        message="Creating a file requires a valid, non-empty filename.",
                    )
                ]
            )
        file_create_builder = FileStorageBuilder(
            filename=file_name_to_create,
            content=data,
            owner_id=owner_id,
            key=str(uuid4()),
        )

        await self.pre_create_hook(file_create_builder)
        created_resource = await self.repository.create(
            builder=file_create_builder
        )
        await self.post_create_hook(created_resource)
        return created_resource

    async def update_by_id(self, id, builder, etag_if_match=None):
        raise NotImplementedError("Update is not supported for file storage")

    async def update_many(self, query, builder):
        raise NotImplementedError("Update is not supported for file storage")

    async def update_one(self, query, builder, etag_if_match=None):
        raise NotImplementedError("Update is not supported for file storage")

    async def _update_resource(
        self, existing_resource, builder, etag_if_match=None
    ):
        raise NotImplementedError("Update is not supported for file storage")
