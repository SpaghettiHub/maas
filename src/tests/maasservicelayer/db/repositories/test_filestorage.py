# Copyright 2025 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).
from base64 import b64decode, b64encode
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncConnection

from maasservicelayer.builders.filestorage import FileStorageBuilder
from maasservicelayer.context import Context
from maasservicelayer.db.filters import QuerySpec
from maasservicelayer.db.repositories.filestorage import (
    FileStorageClauseFactory,
    FileStorageRepository,
)
from maasservicelayer.models.base import ResourceBuilder
from maasservicelayer.models.filestorage import FileStorage
from tests.fixtures.factories.filestorage import create_test_filestorage_entry
from tests.maasapiserver.fixtures.db import Fixture
from tests.maasservicelayer.db.repositories.base import RepositoryCommonTests


class TestFilestorageClauseFactory:
    def test_with_owner_id(self):
        clause = FileStorageClauseFactory.with_owner_id(1)
        assert (
            str(
                clause.condition.compile(
                    compile_kwargs={"literal_binds": True}
                )
            )
            == "maasserver_filestorage.owner_id = 1"
        )

    def test_with_key(self):
        clause = FileStorageClauseFactory.with_key("file_key")
        assert (
            str(
                clause.condition.compile(
                    compile_kwargs={"literal_binds": True}
                )
            )
            == "maasserver_filestorage.key = 'file_key'"
        )

    def test_with_filename(self):
        clause = FileStorageClauseFactory.with_filename("test_file.sh")
        assert (
            str(
                clause.condition.compile(
                    compile_kwargs={"literal_binds": True}
                )
            )
            == "maasserver_filestorage.filename = 'test_file.sh'"
        )

    def test_with_filename_prefix(self):
        clause = FileStorageClauseFactory.with_filename_prefix("maasfile_")
        assert (
            str(
                clause.condition.compile(
                    compile_kwargs={"literal_binds": True}
                )
            )
            == "lower(maasserver_filestorage.filename) LIKE lower('maasfile_%')"
        )


class TestFilestorageRepository(RepositoryCommonTests[FileStorage]):
    @pytest.fixture
    def repository_instance(
        self, db_connection: AsyncConnection
    ) -> FileStorageRepository:
        return FileStorageRepository(context=Context(connection=db_connection))

    @pytest.fixture
    async def _setup_test_list(
        self, fixture: Fixture, num_objects: int
    ) -> list[FileStorage]:
        return [
            await create_test_filestorage_entry(
                fixture,
                key=f"key-{i}",
                filename=f"filename-{i}",
                content=b64encode(f"content-{i}".encode()).decode(),
            )
            for i in range(num_objects)
        ]

    @pytest.fixture
    async def instance_builder(self, *args, **kwargs) -> ResourceBuilder:
        return FileStorageBuilder(
            filename="filename",
            content=b"content",
            key="key",
            owner_id=None,
        )

    @pytest.fixture
    async def instance_builder_model(self) -> type[ResourceBuilder]:
        return FileStorageBuilder

    @pytest.fixture
    async def created_instance(self, fixture: Fixture) -> FileStorage:
        expected_file = await create_test_filestorage_entry(fixture)
        expected_file.content = b64decode(expected_file.content)
        return expected_file

    async def test_get_one_converts_content_str_to_bytes(
        self,
        repository_instance: FileStorageRepository,
        fixture: Fixture,
    ) -> None:
        content = b"expected-content-string"
        encoded_content = b64encode(content).decode()

        await create_test_filestorage_entry(
            fixture,
            content=encoded_content,
        )

        file = await repository_instance.get_one(query=QuerySpec())

        # Ensure returned object got content parsed from str to bytes
        assert type(file.content) is bytes
        assert file.content != encoded_content
        assert file.content == content

    @patch("maasservicelayer.db.repositories.filestorage.b64decode")
    async def test_get_one_doesnt_convert_content_if_none(
        self,
        b64decode_mock: MagicMock,
        repository_instance: FileStorageRepository,
    ) -> None:
        file = await repository_instance.get_one(query=QuerySpec())
        assert file is None
        b64decode_mock.assert_not_called()

    async def test_get_by_id_converts_content_str_to_bytes(
        self,
        repository_instance: FileStorageRepository,
        fixture: Fixture,
    ) -> None:
        id_to_use = 42
        content = b"expected-content-string"
        encoded_content = b64encode(content).decode()

        await create_test_filestorage_entry(
            fixture,
            id=id_to_use,
            content=encoded_content,
        )

        file = await repository_instance.get_by_id(id_to_use)

        assert type(file.content) is bytes
        assert file.content != encoded_content
        assert file.content == content

    @pytest.mark.parametrize("num_objects", [2])
    async def test_get_many_converts_content_str_to_bytes(
        self,
        repository_instance: FileStorageRepository,
        _setup_test_list: list[FileStorage],
        num_objects: int,
    ) -> None:
        files = await repository_instance.get_many(query=QuerySpec())

        for idx, file in enumerate(files):
            expected_content = f"content-{idx}".encode("utf-8")
            encoded_content = b64encode(expected_content).decode()

            assert type(file.content) is bytes
            assert file.content != encoded_content
            assert file.content == expected_content

    async def test_update_one(self, repository_instance, instance_builder):
        with pytest.raises(NotImplementedError):
            return await super().test_update_one(
                repository_instance, instance_builder
            )

    @pytest.mark.parametrize("num_objects", [2])
    async def test_update_one_multiple_results(
        self,
        repository_instance,
        instance_builder_model,
        _setup_test_list,
        num_objects,
    ):
        with pytest.raises(NotImplementedError):
            return await super().test_update_one_multiple_results(
                repository_instance,
                instance_builder_model,
                _setup_test_list,
                num_objects,
            )

    @pytest.mark.parametrize("num_objects", [2])
    async def test_update_many(
        self,
        repository_instance,
        instance_builder_model,
        _setup_test_list,
        num_objects,
    ):
        with pytest.raises(NotImplementedError):
            return await super().test_update_many(
                repository_instance,
                instance_builder_model,
                _setup_test_list,
                num_objects,
            )

    async def test_update_by_id(self, repository_instance, instance_builder):
        with pytest.raises(NotImplementedError):
            return await super().test_update_by_id(
                repository_instance, instance_builder
            )
