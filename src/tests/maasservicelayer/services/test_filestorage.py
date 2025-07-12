#  Copyright 2025 Canonical Ltd.  This software is licensed under the
#  GNU Affero General Public License version 3 (see the file LICENSE).
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from fastapi import UploadFile
import pytest

from maasservicelayer.builders.filestorage import FileStorageBuilder
from maasservicelayer.context import Context
from maasservicelayer.db.repositories.filestorage import FileStorageRepository
from maasservicelayer.exceptions.catalog import (
    AlreadyExistsException,
    BadRequestException,
    BaseExceptionDetail,
)
from maasservicelayer.exceptions.constants import (
    MISSING_FILE_FILENAME_VIOLATION_TYPE,
    UNIQUE_CONSTRAINT_VIOLATION_TYPE,
)
from maasservicelayer.models.filestorage import FileStorage
from maasservicelayer.services.filestorage import FileStorageService
from tests.maasservicelayer.services.base import ServiceCommonTests


@pytest.mark.asyncio
class TestFileStorageService(ServiceCommonTests):
    @pytest.fixture
    def service_instance(self) -> FileStorageService:
        return FileStorageService(
            context=Context(),
            repository=Mock(FileStorageRepository),
        )

    @pytest.fixture
    def test_instance(self) -> FileStorage:
        return FileStorage(
            id=1,
            filename="test_file",
            content="content".encode("utf-8"),
            key="key",
            owner_id=None,
        )

    def create_dummy_binary_upload_file(
        self,
        filename: str | None = "test.bin",
        size_in_bytes: int | None = 1024,
    ) -> UploadFile:
        return UploadFile(
            file=BytesIO(b"0" * size_in_bytes),
            filename=filename,
            size=1024,
        )

    async def test_create(
        self, service_instance, test_instance, builder_model
    ):
        with pytest.raises(NotImplementedError):
            return await super().test_create(
                service_instance, test_instance, builder_model
            )

    @patch("maasservicelayer.services.filestorage.uuid4")
    async def test_create_from_upload(
        self,
        uuid4_mock: MagicMock,
    ) -> None:
        test_file_name = "test.bin"
        test_file_key = "test_file_key"

        test_file = self.create_dummy_binary_upload_file(test_file_name)
        test_file_content = await test_file.read()
        await test_file.seek(0)

        expected_filestorage = FileStorage(
            id=0,
            filename=test_file_name,
            content=test_file_content,
            key=test_file_key,
            owner_id=None,
        )

        uuid4_mock.return_value = test_file_key

        mock_filestorage_repository = Mock(FileStorageRepository)
        mock_filestorage_repository.create.return_value = expected_filestorage

        file_storage_service = FileStorageService(
            context=Context(),
            repository=mock_filestorage_repository,
        )

        created_file = await file_storage_service.create_from_upload(
            file=test_file,
        )

        assert created_file.id == expected_filestorage.id
        assert created_file.filename == expected_filestorage.filename
        assert created_file.content == expected_filestorage.content
        assert created_file.key == expected_filestorage.key
        assert created_file.owner_id == expected_filestorage.owner_id

        mock_filestorage_repository.create.assert_called_once_with(
            builder=FileStorageBuilder(
                filename=test_file_name,
                content=test_file_content,
                key=test_file_key,
                owner_id=None,
            )
        )

    @patch("maasservicelayer.services.filestorage.uuid4")
    async def test_create_from_upload_with_filename(
        self,
        uuid4_mock: MagicMock,
    ) -> None:
        test_file_name = "test.bin"
        test_file_name_override = "my_file_name.bin"
        test_file_key = "test_file_key"

        test_file = self.create_dummy_binary_upload_file(test_file_name)
        test_file_content = await test_file.read()
        await test_file.seek(0)

        expected_filestorage = FileStorage(
            id=0,
            filename=test_file_name,
            content=test_file_content,
            key=test_file_key,
            owner_id=None,
        )

        uuid4_mock.return_value = test_file_key

        mock_filestorage_repository = Mock(FileStorageRepository)
        mock_filestorage_repository.create.return_value = expected_filestorage

        filestorage_service = FileStorageService(
            context=Context(),
            repository=mock_filestorage_repository,
        )

        created_file = await filestorage_service.create_from_upload(
            file=test_file,
            filename=test_file_name_override,
        )

        assert created_file.id == expected_filestorage.id
        assert created_file.filename == expected_filestorage.filename
        assert created_file.content == expected_filestorage.content
        assert created_file.key == expected_filestorage.key
        assert created_file.owner_id == expected_filestorage.owner_id

        mock_filestorage_repository.create.assert_called_once_with(
            builder=FileStorageBuilder(
                filename=test_file_name_override,
                content=test_file_content,
                key=test_file_key,
                owner_id=None,
            )
        )

    @patch("maasservicelayer.services.filestorage.uuid4")
    async def test_create_from_upload_with_owner_id(
        self,
        uuid4_mock: MagicMock,
    ) -> None:
        test_file_name = "test.bin"
        test_file_key = "test_file_key"

        test_file = self.create_dummy_binary_upload_file(test_file_name)
        test_file_content = await test_file.read()
        await test_file.seek(0)

        expected_filestorage = FileStorage(
            id=0,
            filename=test_file_name,
            content=test_file_content,
            key=test_file_key,
            owner_id=42,
        )

        uuid4_mock.return_value = test_file_key

        mock_filestorage_repository = Mock(FileStorageRepository)
        mock_filestorage_repository.create.return_value = expected_filestorage

        filestorage_service = FileStorageService(
            context=Context(),
            repository=mock_filestorage_repository,
        )

        created_file = await filestorage_service.create_from_upload(
            file=test_file,
            owner_id=42,
        )

        assert created_file.id == expected_filestorage.id
        assert created_file.filename == expected_filestorage.filename
        assert created_file.content == expected_filestorage.content
        assert created_file.key == expected_filestorage.key
        assert created_file.owner_id == expected_filestorage.owner_id

        mock_filestorage_repository.create.assert_called_once_with(
            builder=FileStorageBuilder(
                filename=test_file_name,
                content=test_file_content,
                key=test_file_key,
                owner_id=42,
            )
        )

    @patch("maasservicelayer.services.filestorage.uuid4")
    async def test_create_from_upload_empty_file(
        self,
        uuid4_mock: MagicMock,
    ) -> None:
        test_file_name = "test.bin"
        test_file_key = "test_file_key"

        test_file = self.create_dummy_binary_upload_file(test_file_name, 0)
        test_file_content = await test_file.read()
        await test_file.seek(0)

        expected_filestorage = FileStorage(
            id=0,
            filename=test_file_name,
            content=test_file_content,
            key=test_file_key,
            owner_id=None,
        )

        uuid4_mock.return_value = test_file_key

        mock_filestorage_repository = Mock(FileStorageRepository)
        mock_filestorage_repository.create.return_value = expected_filestorage

        filestorage_service = FileStorageService(
            context=Context(),
            repository=mock_filestorage_repository,
        )

        created_file = await filestorage_service.create_from_upload(
            file=test_file,
        )

        assert created_file.id == expected_filestorage.id
        assert created_file.filename == expected_filestorage.filename
        assert created_file.content == expected_filestorage.content
        assert len(created_file.content) == 0
        assert created_file.key == expected_filestorage.key
        assert created_file.owner_id == expected_filestorage.owner_id

        mock_filestorage_repository.create.assert_called_once_with(
            builder=FileStorageBuilder(
                filename=test_file_name,
                content=test_file_content,
                key=test_file_key,
                owner_id=None,
            )
        )

    @patch("maasservicelayer.services.filestorage.uuid4")
    async def test_create_from_upload_already_exists(
        self,
        uuid4_mock: MagicMock,
    ) -> None:
        test_file_name = "test.bin"
        test_file_key = "test_file_key"

        test_file = self.create_dummy_binary_upload_file(test_file_name)
        test_file_content = await test_file.read()
        await test_file.seek(0)

        uuid4_mock.return_value = test_file_key

        mock_filestorage_repository = Mock(FileStorageRepository)
        mock_filestorage_repository.create.side_effect = AlreadyExistsException(
            details=[
                BaseExceptionDetail(
                    type=UNIQUE_CONSTRAINT_VIOLATION_TYPE,
                    message="A resource with such identifiers already exist.",
                )
            ]
        )

        filestorage_service = FileStorageService(
            context=Context(),
            repository=mock_filestorage_repository,
        )

        with pytest.raises(AlreadyExistsException):
            created_file = await filestorage_service.create_from_upload(
                file=test_file,
            )

            assert created_file is None

        mock_filestorage_repository.create.assert_called_once_with(
            builder=FileStorageBuilder(
                filename=test_file_name,
                content=test_file_content,
                key=test_file_key,
                owner_id=None,
            )
        )

    @patch("maasservicelayer.services.filestorage.FileStorageService.create")
    async def test_create_from_upload_fails_when_no_filename(
        self,
        service_create_mock: AsyncMock,
        service_instance: FileStorageService,
    ) -> None:
        test_file = self.create_dummy_binary_upload_file()
        test_file.filename = None

        mock_filestorage_repository = Mock(FileStorageRepository)

        filestorage_service = FileStorageService(
            context=Context(),
            repository=mock_filestorage_repository,
        )

        with pytest.raises(BadRequestException) as e:
            await filestorage_service.create_from_upload(
                file=test_file,
            )

            assert e.type == MISSING_FILE_FILENAME_VIOLATION_TYPE

        mock_filestorage_repository.create.assert_not_called()

    async def test_update_many(
        self, service_instance, test_instance, builder_model
    ):
        with pytest.raises(NotImplementedError):
            return await super().test_update_many(
                service_instance, test_instance, builder_model
            )

    async def test_update_one(
        self, service_instance, test_instance, builder_model
    ):
        with pytest.raises(NotImplementedError):
            return await super().test_update_one(
                service_instance, test_instance, builder_model
            )

    async def test_update_one_not_found(self, service_instance, builder_model):
        with pytest.raises(NotImplementedError):
            return await super().test_update_one_not_found(
                service_instance, builder_model
            )

    async def test_update_one_etag_match(
        self, service_instance, test_instance, builder_model
    ):
        with pytest.raises(NotImplementedError):
            return await super().test_update_one_etag_match(
                service_instance, test_instance, builder_model
            )

    async def test_update_one_etag_not_matching(
        self, service_instance, test_instance, builder_model
    ):
        with pytest.raises(NotImplementedError):
            return await super().test_update_one_etag_not_matching(
                service_instance, test_instance, builder_model
            )

    async def test_update_by_id(
        self, service_instance, test_instance, builder_model
    ):
        with pytest.raises(NotImplementedError):
            return await super().test_update_by_id(
                service_instance, test_instance, builder_model
            )

    async def test_update_by_id_not_found(
        self, service_instance, builder_model
    ):
        with pytest.raises(NotImplementedError):
            return await super().test_update_by_id_not_found(
                service_instance, builder_model
            )

    async def test_update_by_id_etag_match(
        self, service_instance, test_instance, builder_model
    ):
        with pytest.raises(NotImplementedError):
            return await super().test_update_by_id_etag_match(
                service_instance, test_instance, builder_model
            )

    async def test_update_by_id_etag_not_matching(
        self, service_instance, test_instance, builder_model
    ):
        with pytest.raises(NotImplementedError):
            return await super().test_update_by_id_etag_not_matching(
                service_instance, test_instance, builder_model
            )
