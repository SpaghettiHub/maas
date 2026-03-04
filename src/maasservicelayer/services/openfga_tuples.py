# Copyright 2026 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from dataclasses import dataclass

from maascommon.openfga.async_client import OpenFGAClient
from maasservicelayer.builders.openfga_tuple import OpenFGATupleBuilder
from maasservicelayer.context import Context
from maasservicelayer.db.filters import QuerySpec
from maasservicelayer.db.repositories.openfga_tuples import (
    OpenFGATuplesClauseFactory,
    OpenFGATuplesRepository,
)
from maasservicelayer.models.openfga_tuple import OpenFGATuple
from maasservicelayer.services.base import Service, ServiceCache


class UndefinedEntitlementError(Exception):
    """Raised when an entitlement name is not defined in the factory."""


class MAASTupleBuilderFactory:
    MAAS_ENTITLEMENTS = {
        "can_edit_machines": OpenFGATupleBuilder.build_group_can_edit_machines,
        "can_deploy_machines": OpenFGATupleBuilder.build_group_can_deploy_machines,
        "can_view_machines": OpenFGATupleBuilder.build_group_can_view_machines,
        "can_view_available_machines": OpenFGATupleBuilder.build_group_can_view_available_machines,
        "can_edit_global_entities": OpenFGATupleBuilder.build_group_can_edit_global_entities,
        "can_view_global_entities": OpenFGATupleBuilder.build_group_can_view_global_entities,
        "can_edit_controllers": OpenFGATupleBuilder.build_group_can_edit_controllers,
        "can_view_controllers": OpenFGATupleBuilder.build_group_can_view_controllers,
        "can_edit_identities": OpenFGATupleBuilder.build_group_can_edit_identities,
        "can_view_identities": OpenFGATupleBuilder.build_group_can_view_identities,
        "can_edit_configurations": OpenFGATupleBuilder.build_group_can_edit_configurations,
        "can_view_configurations": OpenFGATupleBuilder.build_group_can_view_configurations,
        "can_edit_notifications": OpenFGATupleBuilder.build_group_can_edit_notifications,
        "can_view_notifications": OpenFGATupleBuilder.build_group_can_view_notifications,
        "can_edit_boot_entities": OpenFGATupleBuilder.build_group_can_edit_boot_entities,
        "can_view_boot_entities": OpenFGATupleBuilder.build_group_can_view_boot_entities,
        "can_edit_license_keys": OpenFGATupleBuilder.build_group_can_edit_license_keys,
        "can_view_license_keys": OpenFGATupleBuilder.build_group_can_view_license_keys,
        "can_view_devices": OpenFGATupleBuilder.build_group_can_view_devices,
        "can_view_ipaddresses": OpenFGATupleBuilder.build_group_can_view_ipaddresses,
    }

    @classmethod
    def build_entitlement_tuple(
        cls, group_id: int, entitlement_name: str, resource_id: int
    ) -> OpenFGATupleBuilder:
        if resource_id != 0:
            raise ValueError("Resource ID must be 0 for MAAS entitlements.")
        if entitlement_name not in cls.MAAS_ENTITLEMENTS:
            raise UndefinedEntitlementError(
                f"Entitlement {entitlement_name} is not defined."
            )
        builder_func = cls.MAAS_ENTITLEMENTS[entitlement_name]
        return builder_func(group_id)


class PoolTupleBuilderFactory:
    POOL_ENTITLEMENTS = {
        "can_edit_machines": OpenFGATupleBuilder.build_group_can_edit_machines_in_pool,
        "can_deploy_machines": OpenFGATupleBuilder.build_group_can_deploy_machines_in_pool,
        "can_view_machines": OpenFGATupleBuilder.build_group_can_view_machines_in_pool,
        "can_view_available_machines": OpenFGATupleBuilder.build_group_can_view_available_machines_in_pool,
    }

    @classmethod
    def build_entitlement_tuple(
        cls, group_id: int, entitlement_name: str, pool_id: int
    ) -> OpenFGATupleBuilder:
        if entitlement_name not in cls.POOL_ENTITLEMENTS:
            raise UndefinedEntitlementError(
                f"Entitlement {entitlement_name} is not defined."
            )
        builder_func = cls.POOL_ENTITLEMENTS[entitlement_name]
        return builder_func(group_id, str(pool_id))


class EntitlementsBuilderFactory:
    FACTORIES = {
        "maas": MAASTupleBuilderFactory,
        "pool": PoolTupleBuilderFactory,
    }

    @classmethod
    def build_openfga_tuple(
        cls,
        group_id: int,
        entitlement_name: str,
        resource_type: str,
        resource_id: int,
    ) -> OpenFGATupleBuilder:
        if resource_type not in cls.FACTORIES:
            raise ValueError(
                f"Resource type {resource_type} is not supported."
            )
        factory = cls.FACTORIES[resource_type]
        return factory.build_entitlement_tuple(
            group_id, entitlement_name, resource_id
        )


@dataclass(slots=True)
class OpenFGAServiceCache(ServiceCache):
    client: OpenFGAClient | None = None

    async def close(self) -> None:
        if self.client:
            await self.client.close()


class OpenFGATupleService(Service):
    def __init__(
        self,
        context: Context,
        openfga_tuple_repository: OpenFGATuplesRepository,
        cache: ServiceCache,
    ):
        super().__init__(context, cache)
        self.openfga_tuple_repository = openfga_tuple_repository

    @staticmethod
    def build_cache_object() -> OpenFGAServiceCache:
        return OpenFGAServiceCache()

    @Service.from_cache_or_execute(attr="client")
    async def get_client(self) -> OpenFGAClient:
        return OpenFGAClient()

    async def get_many(self, query: QuerySpec) -> list[OpenFGATuple]:
        return await self.openfga_tuple_repository.get_many(query)

    async def upsert(self, builder: OpenFGATupleBuilder) -> OpenFGATuple:
        return await self.openfga_tuple_repository.upsert(builder)

    async def delete_many(self, query: QuerySpec) -> None:
        return await self.openfga_tuple_repository.delete_many(query)

    async def delete_pool(self, pool_id: int) -> None:
        query = QuerySpec(
            where=OpenFGATuplesClauseFactory.and_clauses(
                [
                    OpenFGATuplesClauseFactory.with_object_id(str(pool_id)),
                    OpenFGATuplesClauseFactory.with_object_type("pool"),
                    OpenFGATuplesClauseFactory.with_relation("parent"),
                ]
            )
        )
        await self.delete_many(query)

    async def delete_user(self, user_id: int) -> None:
        query = QuerySpec(
            where=OpenFGATuplesClauseFactory.and_clauses(
                [
                    OpenFGATuplesClauseFactory.with_user(f"user:{user_id}"),
                    OpenFGATuplesClauseFactory.with_relation("member"),
                ]
            )
        )
        await self.delete_many(query)

    async def delete_group(self, group_id: int) -> None:
        # Delete users who are members of this group AND entitlement tuples associated with this group
        membership_query = QuerySpec(
            where=OpenFGATuplesClauseFactory.or_clauses(
                [
                    OpenFGATuplesClauseFactory.and_clauses(
                        [
                            OpenFGATuplesClauseFactory.with_object_type(
                                "group"
                            ),
                            OpenFGATuplesClauseFactory.with_object_id(
                                str(group_id)
                            ),
                        ]
                    ),
                    OpenFGATuplesClauseFactory.with_user(
                        f"group:{group_id}#member"
                    ),
                ]
            )
        )
        await self.delete_many(membership_query)

    async def remove_user_from_group(
        self, group_id: int, user_id: int
    ) -> None:
        query = QuerySpec(
            where=OpenFGATuplesClauseFactory.and_clauses(
                [
                    OpenFGATuplesClauseFactory.with_user(f"user:{user_id}"),
                    OpenFGATuplesClauseFactory.with_relation("member"),
                    OpenFGATuplesClauseFactory.with_object_type("group"),
                    OpenFGATuplesClauseFactory.with_object_id(str(group_id)),
                ]
            )
        )
        await self.delete_many(query)
