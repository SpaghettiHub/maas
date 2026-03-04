# Copyright 2026 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from pydantic import BaseModel, Field


class EntitlementRequest(BaseModel):
    resource_type: str = Field(
        description="The resource type (e.g. 'maas', 'pool')."
    )
    resource_id: int = Field(
        description="The resource ID. Must be 0 for 'maas' type."
    )
    entitlement: str = Field(description="The entitlement name.")
