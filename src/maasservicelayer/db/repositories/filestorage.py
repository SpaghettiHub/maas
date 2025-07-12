#  Copyright 2025 Canonical Ltd.  This software is licensed under the
#  GNU Affero General Public License version 3 (see the file LICENSE).

from base64 import b64decode
from operator import eq
from typing import List

from sqlalchemy import insert, Table
from sqlalchemy.exc import IntegrityError

from maasservicelayer.db.filters import Clause, ClauseFactory, QuerySpec
from maasservicelayer.db.mappers.base import BaseDomainDataMapper
from maasservicelayer.db.mappers.filestorage import FileStorageDomainDataMapper
from maasservicelayer.db.repositories.base import BaseRepository
from maasservicelayer.db.tables import FileStorageTable
from maasservicelayer.models.base import ResourceBuilder
from maasservicelayer.models.filestorage import FileStorage
from maasservicelayer.utils.date import utcnow


class FileStorageClauseFactory(ClauseFactory):
    @classmethod
    def with_filename(cls, filename: str) -> Clause:
        return Clause(condition=eq(FileStorageTable.c.filename, filename))

    @classmethod
    def with_filename_prefix(cls, prefix: str) -> Clause:
        return Clause(
            condition=FileStorageTable.c.filename.ilike(f"{prefix}%")
        )

    @classmethod
    def with_key(cls, key: str) -> Clause:
        return Clause(condition=eq(FileStorageTable.c.key, key))

    @classmethod
    def with_owner_id(cls, owner_id: int) -> Clause:
        return Clause(condition=eq(FileStorageTable.c.owner_id, owner_id))


class FileStorageRepository(BaseRepository[FileStorage]):
    def get_repository_table(self) -> Table:
        return FileStorageTable

    def get_model_factory(self) -> type[FileStorage]:
        return FileStorage

    def get_mapper(self) -> BaseDomainDataMapper:
        return FileStorageDomainDataMapper(self.get_repository_table())

    async def create(self, builder: ResourceBuilder) -> FileStorage:
        resource = self.mapper.build_resource(builder)
        if self.has_timestamped_fields:
            # Populate the fields only if the caller did not set them.
            now = utcnow()
            resource["created"] = resource.get("created", now)
            resource["updated"] = resource.get("updated", now)
        stmt = (
            insert(self.get_repository_table())
            .returning(self.get_repository_table())
            .values(**resource.get_values())
        )
        try:
            result = (await self.execute_stmt(stmt)).one()
            result_dict = result._asdict()
            result_dict["content"] = b64decode(result_dict["content"])
            return self.get_model_factory()(**result_dict)
        except IntegrityError:
            self._raise_already_existing_exception()

    async def _get(self, query: QuerySpec) -> List[FileStorage]:
        """
        This override is required to convert the string-based, base64-encoded
        file content that the database uses, to a valid `bytes` representation
        used by the service layer model.

        This is called by `get_one`, `get_by_id`, and `get_many. In the future,
        if this `list` is ever used over `get_many`, then that will need
        overriding also.
        """
        stmt = self.select_all_statement()
        stmt = query.enrich_stmt(stmt)

        result = (await self.execute_stmt(stmt)).all()
        stored_files = []
        for row in result:
            row_dict = row._asdict()
            row_dict["content"] = b64decode(row_dict["content"])
            stored_files.append(self.get_model_factory()(**row_dict))
        return stored_files

    async def update_one(self, query, builder):
        raise NotImplementedError("Update is not supported for file storage")

    async def update_many(self, query, builder):
        raise NotImplementedError("Update is not supported for file storage")

    async def update_by_id(self, id, builder):
        raise NotImplementedError("Update is not supported for file storage")

    async def _update(self, query, builder):
        raise NotImplementedError("Update is not supported for file storage")
