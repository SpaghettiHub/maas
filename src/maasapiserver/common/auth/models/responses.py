#  Copyright 2024 Canonical Ltd.  This software is licensed under the
#  GNU Affero General Public License version 3 (see the file LICENSE).

from collections.abc import Sequence
from typing import Any, Optional, Union

from pydantic import BaseModel, Field, validator

from maasapiserver.common.auth.models import (
    ALL_RESOURCES,
    AllResourcesType,
    Resource,
)


class UserDetailsResponse(BaseModel):
    username: str
    fullname: Optional[str] = Field(validation_alias="name")
    email: Optional[str]


class GetGroupsResponse(BaseModel):
    groups: Sequence[str]


class ResourceListResponse(BaseModel):
    resources: Sequence[Resource]


class UpdateResourcesResponse(BaseModel):
    sync_id: str = Field(alias="sync-id")


class PermissionResourcesMapping(BaseModel):
    permission: str
    resources: Union[Sequence[int], AllResourcesType]

    @validator("resources", pre=True)
    def preprocess_resources(cls, data: Any):
        if data == [""]:
            return ALL_RESOURCES
        if isinstance(data, list):
            return [int(id) for id in data]
        return data


class AllowedForUserResponse(BaseModel):
    permissions: Sequence[PermissionResourcesMapping]
