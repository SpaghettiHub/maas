# Copyright 2024-2025 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from collections.abc import Sequence
from typing import TypeVar

import pytest
from sqlalchemy.ext.asyncio import AsyncConnection

from maasservicelayer.builders.domains import DomainBuilder
from maasservicelayer.context import Context
from maasservicelayer.db.repositories.base import BaseRepository
from maasservicelayer.db.repositories.domains import DomainsRepository
from maasservicelayer.models.base import (
    MaasTimestampedBaseModel,
    ResourceBuilder,
)
from maasservicelayer.models.domains import Domain
from tests.fixtures.factories.domain import create_test_domain_entry
from tests.fixtures.factories.forwarddnsserver import (
    create_test_forwarddnsserver_entry,
)
from tests.maasapiserver.fixtures.db import Fixture
from tests.maasservicelayer.db.repositories.base import RepositoryCommonTests

T = TypeVar("T", bound=MaasTimestampedBaseModel)


@pytest.mark.asyncio
class TestDomainsRepository(RepositoryCommonTests[Domain]):
    @pytest.fixture
    def repository_instance(
        self, db_connection: AsyncConnection
    ) -> DomainsRepository:
        return DomainsRepository(Context(connection=db_connection))

    @pytest.fixture
    async def _setup_test_list(
        self, fixture: Fixture, num_objects: int
    ) -> Sequence[Domain]:
        return [
            await create_test_domain_entry(fixture) for _ in range(num_objects)
        ]

    @pytest.fixture
    async def created_instance(self, fixture: Fixture) -> Domain:
        return await create_test_domain_entry(fixture)

    @pytest.fixture
    async def instance_builder(self, fixture: Fixture) -> DomainBuilder:
        return DomainBuilder(name="test_name", authoritative=True)

    @pytest.fixture
    async def instance_builder_model(self) -> type[DomainBuilder]:
        return DomainBuilder

    @pytest.mark.parametrize("num_objects", [10])
    @pytest.mark.parametrize("page_size", range(1, 12))
    async def test_list(
        self,
        page_size: int,
        repository_instance: BaseRepository,
        _setup_test_list: Sequence[T],
        num_objects: int,
    ):
        # delete default domain first
        await repository_instance.delete_by_id(0)
        await super().test_list(
            page_size, repository_instance, _setup_test_list, num_objects
        )

    @pytest.mark.parametrize("num_objects", [3])
    async def test_delete_many(
        self,
        repository_instance: BaseRepository,
        _setup_test_list: Sequence[T],
        num_objects: int,
    ):
        # delete default domain first
        await repository_instance.delete_by_id(0)
        await super().test_delete_many(
            repository_instance, _setup_test_list, num_objects
        )

    @pytest.mark.parametrize("num_objects", [3])
    async def test_get_many(
        self,
        repository_instance: BaseRepository,
        _setup_test_list: Sequence[T],
        num_objects: int,
    ):
        await repository_instance.delete_by_id(0)
        await super().test_get_many(
            repository_instance, _setup_test_list, num_objects
        )

    @pytest.mark.parametrize("num_objects", [2])
    async def test_update_many(
        self,
        repository_instance: BaseRepository,
        instance_builder_model: type[ResourceBuilder],
        _setup_test_list: Sequence[T],
        num_objects: int,
    ):
        await repository_instance.delete_by_id(0)
        await super().test_update_many(
            repository_instance,
            instance_builder_model,
            _setup_test_list,
            num_objects,
        )

    @pytest.mark.skip(reason="Not applicable")
    async def test_create_duplicated(
        self, repository_instance, instance_builder
    ):
        pass

    async def test_get_forwarded_domains(
        self, repository_instance: DomainsRepository, fixture: Fixture
    ) -> None:
        domains = [
            await create_test_domain_entry(
                fixture, name=f"test-domain-{i}", authoritative=False
            )
            for i in range(3)
        ]
        fwd_srvrs = [
            await create_test_forwarddnsserver_entry(
                fixture, ip_address=f"10.0.0.{i + 1}", domain=domain
            )
            for i, domain in enumerate(domains)
        ]

        fwd_domains = await repository_instance.get_forwarded_domains()

        assert len(fwd_domains) == len(domains)

        for fwd_domain, fwd_srvr in fwd_domains:
            assert fwd_domain.id in [domain.id for domain in domains]
            assert fwd_domain.name in [domain.name for domain in domains]
            assert fwd_srvr.ip_address in [
                fwd_srvr.ip_address for fwd_srvr in fwd_srvrs
            ]
            assert fwd_srvr.port == 53
