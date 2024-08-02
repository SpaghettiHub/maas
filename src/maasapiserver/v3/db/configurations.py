from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncConnection
from sqlalchemy.sql.operators import eq

from maasapiserver.v3.models.configurations import Configuration
from maasservicelayer.db.tables import ConfigTable


class ConfigurationsRepository:
    def __init__(self, connection: AsyncConnection):
        self.connection = connection

    async def get(self, name: str) -> Configuration | None:
        stmt = (
            select(
                "*",
            )
            .select_from(ConfigTable)
            .where(eq(ConfigTable.c.name, name))
        )
        result = (await self.connection.execute(stmt)).one_or_none()
        return Configuration(**result._asdict()) if result else None
