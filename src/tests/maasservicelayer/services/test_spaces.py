# Copyright 2024 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from unittest.mock import Mock

import pytest
from pytest_mock import MockerFixture

from maasservicelayer.context import Context
from maasservicelayer.db.filters import QuerySpec
from maasservicelayer.db.repositories.spaces import (
    SpaceResourceBuilder,
    SpacesRepository,
)
from maasservicelayer.db.repositories.vlans import (
    VlanResourceBuilder,
    VlansClauseFactory,
)
from maasservicelayer.exceptions.catalog import PreconditionFailedException
from maasservicelayer.exceptions.constants import (
    ETAG_PRECONDITION_VIOLATION_TYPE,
)
from maasservicelayer.models.base import ListResult, MaasBaseModel
from maasservicelayer.models.spaces import Space
from maasservicelayer.services._base import BaseService
from maasservicelayer.services.spaces import SpacesService
from maasservicelayer.services.vlans import VlansService
from maasservicelayer.utils.date import utcnow
from tests.maasservicelayer.services.base import ServiceCommonTests


@pytest.mark.asyncio
class TestCommonSpacesService(ServiceCommonTests):
    @pytest.fixture
    def service_instance(self) -> BaseService:
        return SpacesService(
            context=Context(),
            vlans_service=Mock(VlansService),
            spaces_repository=Mock(SpacesRepository),
        )

    @pytest.fixture
    def test_instance(self) -> MaasBaseModel:
        return Space(
            id=1,
            name="test_space_name",
            description="test_space_description",
            created=utcnow(),
            updated=utcnow(),
        )
