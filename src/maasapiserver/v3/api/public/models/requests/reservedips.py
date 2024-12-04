# Copyright 2024 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from pydantic import BaseModel, Field, IPvAnyAddress

from maasservicelayer.db.filters import QuerySpec
from maasservicelayer.db.repositories.reservedips import (
    ReservedIPsResourceBuilder,
)
from maasservicelayer.db.repositories.staticipaddress import (
    StaticIPAddressClauseFactory,
)
from maasservicelayer.exceptions.catalog import (
    BaseExceptionDetail,
    ValidationException,
)
from maasservicelayer.exceptions.constants import (
    INVALID_ARGUMENT_VIOLATION_TYPE,
)
from maasservicelayer.services import ServiceCollectionV3
from maasservicelayer.utils.date import utcnow
from maasservicelayer.utils.validators import MacAddress


class ReservedIPCreateRequest(BaseModel):
    ip: IPvAnyAddress = Field(description="The IP to be reserved.")
    mac_address: MacAddress = Field(
        description="The MAC address that should be linked to the reserved IP."
    )
    subnet_id: int | None = Field(
        description="ID of the subnet associated with the IP to be reserved. ",
        default=None,
    )
    comment: str | None = Field(
        description="A description of this reserved IP.", default=None
    )

    async def to_builder(
        self, services: ServiceCollectionV3
    ) -> ReservedIPsResourceBuilder:
        existing_ip = await services.staticipaddress.get_one(
            QuerySpec(where=StaticIPAddressClauseFactory.with_ip(self.ip))
        )
        if existing_ip is not None:
            mac_addresses = await services.staticipaddress.get_mac_addresses(
                query=QuerySpec(
                    where=StaticIPAddressClauseFactory.with_id(existing_ip.id)
                )
            )
            if self.mac_address not in mac_addresses:
                raise ValidationException.build_for_field(
                    "ip",
                    f"The ip {self.ip} is already in use by another machine.",
                )

        if self.subnet_id:
            dynamic_range = await services.ipranges.get_dynamic_range_for_ip(
                self.subnet_id, self.ip
            )
            if dynamic_range is not None:
                raise ValidationException.build_for_field(
                    "ip",
                    f"The ip {self.ip} must be outside the dynamic range {dynamic_range.start_ip} - {dynamic_range.end_ip}.",
                )
        else:
            subnet = await services.subnets.find_best_subnet_for_ip(self.ip)
            if subnet is None:
                raise ValidationException(
                    details=[
                        BaseExceptionDetail(
                            type=INVALID_ARGUMENT_VIOLATION_TYPE,
                            message=f"Could not find a suitable subnet for {self.ip}. Please create the subnet first.",
                        )
                    ]
                )
            if self.ip not in subnet.cidr:
                raise ValidationException.build_for_field(
                    "ip", "The provided ip is not part of the subnet."
                )
            if self.ip == subnet.cidr.network_address:
                raise ValidationException.build_for_field(
                    "ip", "The network address cannot be a reserved IP."
                )
            if self.ip == subnet.cidr.broadcast_address:
                raise ValidationException.build_for_field(
                    "ip", "The broadcast address cannot be a reserved IP."
                )
            self.subnet_id = subnet.id
        now = utcnow()
        builder = (
            ReservedIPsResourceBuilder()
            .with_ip(self.ip)
            .with_mac_address(self.mac_address)
            .with_subnet_id(self.subnet_id)
            .with_comment(self.comment)
            .with_created(now)
            .with_updated(now)
        )
        return builder
