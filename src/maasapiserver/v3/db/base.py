from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from sqlalchemy.ext.asyncio import AsyncConnection

from maasapiserver.v3.api.models.requests.query import PaginationParams
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
    async def create(self, request: T) -> T:
        pass

    @abstractmethod
    async def find_by_id(self, id: int) -> T | None:
        pass

    @abstractmethod
    async def list(self, pagination_params: PaginationParams) -> ListResult[T]:
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
