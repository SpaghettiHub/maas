# Copyright 2026 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).
from unittest.mock import Mock

import pytest
from sqlalchemy import and_
from sqlalchemy.sql.operators import eq

from maasservicelayer.builders.openfga_tuple import OpenFGATupleBuilder
from maasservicelayer.context import Context
from maasservicelayer.db.filters import QuerySpec
from maasservicelayer.db.repositories.openfga_tuples import (
    OpenFGATuplesClauseFactory,
    OpenFGATuplesRepository,
)
from maasservicelayer.db.tables import OpenFGATupleTable
from maasservicelayer.services import OpenFGATupleService, ServiceCollectionV3
from maasservicelayer.services.openfga_tuples import (
    EntitlementsBuilderFactory,
    MAASTupleBuilderFactory,
    OpenFGAServiceCache,
    PoolTupleBuilderFactory,
    UndefinedEntitlementError,
)
from tests.fixtures.factories.openfga_tuples import create_openfga_tuple
from tests.maasapiserver.fixtures.db import Fixture


@pytest.mark.asyncio
class TestIntegrationOpenFGAService:
    async def test_upsert(
        self,
        fixture: Fixture,
        services: ServiceCollectionV3,
    ):
        await services.openfga_tuples.upsert(
            OpenFGATupleBuilder.build_pool("1000")
        )
        retrieved_pool = await fixture.get(
            OpenFGATupleTable.fullname,
            and_(
                eq(OpenFGATupleTable.c.object_type, "pool"),
                eq(OpenFGATupleTable.c.object_id, "1000"),
            ),
        )
        assert len(retrieved_pool) == 1
        assert retrieved_pool[0]["_user"] == "maas:0"
        assert retrieved_pool[0]["object_type"] == "pool"
        assert retrieved_pool[0]["object_id"] == "1000"
        assert retrieved_pool[0]["relation"] == "parent"

    async def test_upsert_overrides(
        self,
        fixture: Fixture,
        services: ServiceCollectionV3,
    ):
        await create_openfga_tuple(
            fixture, "user:1", "user", "member", "group", "2000"
        )

        await services.openfga_tuples.upsert(
            OpenFGATupleBuilder.build_user_member_group(1, 2000)
        )

        retrieved_tuple = await fixture.get(
            OpenFGATupleTable.fullname,
            and_(
                eq(OpenFGATupleTable.c.object_type, "group"),
                eq(OpenFGATupleTable.c.object_id, "2000"),
                eq(OpenFGATupleTable.c._user, "user:1"),
            ),
        )
        assert len(retrieved_tuple) == 1
        assert retrieved_tuple[0]["_user"] == "user:1"
        assert retrieved_tuple[0]["object_type"] == "group"
        assert retrieved_tuple[0]["object_id"] == "2000"
        assert retrieved_tuple[0]["relation"] == "member"

    async def test_delete_many(
        self, fixture: Fixture, services: ServiceCollectionV3
    ):
        await create_openfga_tuple(
            fixture, "user:1", "user", "member", "group", "2000"
        )
        await services.openfga_tuples.delete_many(
            QuerySpec(where=OpenFGATuplesClauseFactory.with_user("user:1"))
        )
        retrieved_tuple = await fixture.get(
            OpenFGATupleTable.fullname,
            and_(
                eq(OpenFGATupleTable.c.object_type, "group"),
                eq(OpenFGATupleTable.c.object_id, "2000"),
                eq(OpenFGATupleTable.c._user, "user:1"),
            ),
        )
        assert len(retrieved_tuple) == 0

    async def test_delete_pool(
        self, fixture: Fixture, services: ServiceCollectionV3
    ):
        await create_openfga_tuple(
            fixture, "maas:0", "user", "parent", "pool", "100"
        )
        await services.openfga_tuples.delete_pool(100)
        retrieved_tuple = await fixture.get(
            OpenFGATupleTable.fullname,
            and_(
                eq(OpenFGATupleTable.c.object_type, "pool"),
                eq(OpenFGATupleTable.c.object_id, "100"),
                eq(OpenFGATupleTable.c._user, "maas:0"),
            ),
        )
        assert len(retrieved_tuple) == 0

    async def test_delete_user(
        self, fixture: Fixture, services: ServiceCollectionV3
    ):
        await create_openfga_tuple(
            fixture, "user:1", "user", "member", "group", "2000"
        )
        await services.openfga_tuples.delete_user(1)
        retrieved_tuple = await fixture.get(
            OpenFGATupleTable.fullname,
            and_(
                eq(OpenFGATupleTable.c.object_type, "group"),
                eq(OpenFGATupleTable.c.object_id, "2000"),
                eq(OpenFGATupleTable.c._user, "user:1"),
            ),
        )
        assert len(retrieved_tuple) == 0

    async def test_remove_user_from_group(
        self, fixture: Fixture, services: ServiceCollectionV3
    ):
        await create_openfga_tuple(
            fixture, "user:1", "user", "member", "group", "2000"
        )
        await services.openfga_tuples.remove_user_from_group(2000, 1)
        retrieved_tuple = await fixture.get(
            OpenFGATupleTable.fullname,
            and_(
                eq(OpenFGATupleTable.c.object_type, "group"),
                eq(OpenFGATupleTable.c.object_id, "2000"),
                eq(OpenFGATupleTable.c._user, "user:1"),
            ),
        )
        assert len(retrieved_tuple) == 0


@pytest.mark.asyncio
class TestOpenFGAService:
    async def test_get_client_is_cached(self) -> None:
        cache = OpenFGAServiceCache()
        agents_service = OpenFGATupleService(
            context=Context(),
            openfga_tuple_repository=Mock(OpenFGATuplesRepository),
            cache=cache,
        )

        agents_service2 = OpenFGATupleService(
            context=Context(),
            openfga_tuple_repository=Mock(OpenFGATuplesRepository),
            cache=cache,
        )

        apiclient = await agents_service.get_client()
        apiclient_again = await agents_service.get_client()

        apiclient2 = await agents_service2.get_client()
        apiclient2_again = await agents_service2.get_client()

        assert (
            id(apiclient)
            == id(apiclient2)
            == id(apiclient_again)
            == id(apiclient2_again)
        )


class TestMAASTupleBuilderFactory:
    @pytest.mark.parametrize(
        "entitlement_name",
        list(MAASTupleBuilderFactory.MAAS_ENTITLEMENTS.keys()),
    )
    def test_build_all_maas_entitlements(self, entitlement_name: str) -> None:
        group_id = 42
        result = MAASTupleBuilderFactory.build_entitlement_tuple(
            group_id, entitlement_name, 0
        )
        assert result.user == f"group:{group_id}#member"
        assert result.user_type == "userset"
        assert result.relation == entitlement_name
        assert result.object_type == "maas"
        assert result.object_id == "0"

    def test_rejects_nonzero_resource_id(self) -> None:
        with pytest.raises(
            ValueError, match="Resource ID must be 0 for MAAS entitlements"
        ):
            MAASTupleBuilderFactory.build_entitlement_tuple(
                1, "can_edit_machines", 5
            )

    def test_rejects_undefined_entitlement(self) -> None:
        with pytest.raises(UndefinedEntitlementError, match="not defined"):
            MAASTupleBuilderFactory.build_entitlement_tuple(
                1, "nonexistent", 0
            )


class TestPoolTupleBuilderFactory:
    @pytest.mark.parametrize(
        "entitlement_name",
        list(PoolTupleBuilderFactory.POOL_ENTITLEMENTS.keys()),
    )
    def test_build_all_pool_entitlements(self, entitlement_name: str) -> None:
        group_id = 10
        pool_id = 99
        result = PoolTupleBuilderFactory.build_entitlement_tuple(
            group_id, entitlement_name, pool_id
        )
        assert result.user == f"group:{group_id}#member"
        assert result.user_type == "userset"
        assert result.relation == entitlement_name
        assert result.object_type == "pool"
        assert result.object_id == str(pool_id)

    def test_rejects_undefined_entitlement(self) -> None:
        with pytest.raises(UndefinedEntitlementError, match="not defined"):
            PoolTupleBuilderFactory.build_entitlement_tuple(
                1, "can_edit_identities", 5
            )


class TestEntitlementsBuilderFactory:
    def test_routes_to_maas_factory(self) -> None:
        result = EntitlementsBuilderFactory.build_openfga_tuple(
            1, "can_edit_machines", "maas", 0
        )
        assert result.object_type == "maas"
        assert result.object_id == "0"
        assert result.relation == "can_edit_machines"

    def test_routes_to_pool_factory(self) -> None:
        result = EntitlementsBuilderFactory.build_openfga_tuple(
            1, "can_edit_machines", "pool", 7
        )
        assert result.object_type == "pool"
        assert result.object_id == "7"
        assert result.relation == "can_edit_machines"

    def test_rejects_unsupported_resource_type(self) -> None:
        with pytest.raises(
            ValueError, match="Resource type unknown is not supported"
        ):
            EntitlementsBuilderFactory.build_openfga_tuple(
                1, "can_edit_machines", "unknown", 0
            )

    def test_propagates_maas_validation_error(self) -> None:
        with pytest.raises(ValueError, match="Resource ID must be 0"):
            EntitlementsBuilderFactory.build_openfga_tuple(
                1, "can_edit_machines", "maas", 5
            )

    def test_propagates_undefined_entitlement_error(self) -> None:
        with pytest.raises(UndefinedEntitlementError, match="not defined"):
            EntitlementsBuilderFactory.build_openfga_tuple(
                1, "nonexistent", "maas", 0
            )
