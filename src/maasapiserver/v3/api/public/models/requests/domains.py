# Copyright 2025 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from typing import Optional

from pydantic import Field, validator

from maasapiserver.v3.api.public.models.requests.base import NamedBaseModel
from maasservicelayer.builders.domains import DomainBuilder


class DomainRequest(NamedBaseModel):
    name: str
    authoritative: bool = Field(default=True)
    ttl: Optional[int]

    @validator("ttl")
    def check_ttl(cls, v: int) -> int:
        if v is not None:
            if v < 1 or v > 604800:
                raise ValueError("Invalid value for ttl")
        return v

    def to_builder(self) -> DomainBuilder:
        return DomainBuilder(
            name=self.name, authoritative=self.authoritative, ttl=self.ttl
        )
