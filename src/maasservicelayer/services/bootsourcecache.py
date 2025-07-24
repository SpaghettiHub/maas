# Copyright 2025 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from maasservicelayer.builders.bootsourcecache import BootSourceCacheBuilder
from maasservicelayer.context import Context
from maasservicelayer.db.filters import QuerySpec
from maasservicelayer.db.repositories.bootsourcecache import (
    BootSourceCacheClauseFactory,
    BootSourceCacheRepository,
)
from maasservicelayer.models.bootsourcecache import BootSourceCache
from maasservicelayer.services.base import BaseService, ServiceCache


class BootSourceCacheService(
    BaseService[
        BootSourceCache, BootSourceCacheRepository, BootSourceCacheBuilder
    ]
):
    def __init__(
        self,
        context: Context,
        repository: BootSourceCacheRepository,
        cache: ServiceCache | None = None,
    ):
        super().__init__(context, repository, cache)

    async def create_or_update(
        self, builder: BootSourceCacheBuilder
    ) -> BootSourceCache:
        existing = await self.get_one(
            query=QuerySpec(
                where=BootSourceCacheClauseFactory.and_clauses(
                    [
                        BootSourceCacheClauseFactory.with_boot_source_id(
                            builder.safe_get(builder.boot_source_id)
                        ),
                        BootSourceCacheClauseFactory.with_os(
                            builder.safe_get(builder.os)
                        ),
                        BootSourceCacheClauseFactory.with_arch(
                            builder.safe_get(builder.arch)
                        ),
                        BootSourceCacheClauseFactory.with_subarch(
                            builder.safe_get(builder.subarch)
                        ),
                        BootSourceCacheClauseFactory.with_release(
                            builder.safe_get(builder.release)
                        ),
                        BootSourceCacheClauseFactory.with_label(
                            builder.safe_get(builder.label)
                        ),
                        BootSourceCacheClauseFactory.with_kflavor(
                            builder.safe_get(builder.kflavor)
                        ),
                    ]
                )
            )
        )
        if existing:
            return await self._update_resource(existing, builder)
        return await self.create(builder)
