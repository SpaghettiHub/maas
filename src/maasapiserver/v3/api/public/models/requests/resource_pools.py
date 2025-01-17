# Copyright 2024-2025 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from maasapiserver.v3.api.public.models.requests.base import NamedBaseModel
from maasservicelayer.models.resource_pools import ResourcePoolBuilder


class ResourcePoolRequest(NamedBaseModel):
    description: str

    def to_builder(self) -> ResourcePoolBuilder:
        return ResourcePoolBuilder(
            name=self.name,
            description=self.description,
        )
