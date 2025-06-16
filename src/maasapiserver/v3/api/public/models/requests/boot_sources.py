#  Copyright 2025 Canonical Ltd.  This software is licensed under the
#  GNU Affero General Public License version 3 (see the file LICENSE).

from pydantic import BaseModel, Field


class BootSourcesRequest(BaseModel):
    url: str = Field(
        description="URL of SimpleStreams server providing boot source information."
    )

    keyring: str | None = Field(
        default=None,
        description="Keyring to use for verifying signatures of the boot sources.",
    )
    validate_products: bool = Field(
        default=True,
        description="Whether to validate products in the boot sources.",
    )
