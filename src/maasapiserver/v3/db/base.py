from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from sqlalchemy.ext.asyncio import AsyncConnection

from maasapiserver.common.models.constants import (
    UNIQUE_CONSTRAINT_VIOLATION_TYPE,
)
from maasapiserver.common.models.exceptions import (
    AlreadyExistsException,
    BaseExceptionDetail,
)
from maasapiserver.v3.models.base import ListResult

T = TypeVar("T")


class BaseRepository(ABC, Generic[T]):
    def __init__(self, connection: AsyncConnection):
        self.connection = connection

    @abstractmethod
    async def get_next_id(self) -> int:
        """
        Get the next ID for a new resource. Usually, this is useful because the ID comes from a sequence defined in the
        database.
        """
        pass

    @abstractmethod
    async def create(self, resource: T) -> T:
        pass

    @abstractmethod
    async def find_by_id(self, id: int) -> T | None:
        pass

    @abstractmethod
    async def list(self, token: str | None, size: int) -> ListResult[T]:
        pass

    @abstractmethod
    async def update(self, resource: T) -> T:
        pass

    @abstractmethod
    async def delete(self, id: int) -> None:
        """
        If no resource with such `id` is found, silently ignore it and return `None` in any case.
        """
        pass

    def _raise_already_existing_exception(
        self, name: str, extra_details: str = ""
    ):
        raise AlreadyExistsException(
            details=[
                BaseExceptionDetail(
                    type=UNIQUE_CONSTRAINT_VIOLATION_TYPE,
                    message=f"An entity named '{name}' already exists. {extra_details}",
                )
            ]
        )
