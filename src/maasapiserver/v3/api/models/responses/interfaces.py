from enum import Enum
from ipaddress import IPv4Address, IPv6Address
from typing import Optional, Union

from pydantic import BaseModel, Field

from maasapiserver.v3.api.models.responses.base import (
    BaseHal,
    HalResponse,
    PaginatedResponse,
)
from maasserver.enum import INTERFACE_LINK_TYPE_CHOICES, INTERFACE_TYPE_CHOICES

InterfaceTypeEnum = Enum(
    "InterfaceType",
    dict({str(name).lower(): str(name) for name, _ in INTERFACE_TYPE_CHOICES}),
)
LinkModeEnum = Enum(
    "IpMode",
    dict({str(name): str(name) for name, _ in INTERFACE_LINK_TYPE_CHOICES}),
)


class LinkResponse(BaseModel):
    id: int
    mode: LinkModeEnum
    ip_address: Optional[Union[IPv4Address, IPv6Address]]


class InterfaceResponse(HalResponse[BaseHal]):
    kind = "Interface"
    id: int
    name: str
    type: InterfaceTypeEnum
    mac_address: str
    # TODO
    # effective_mtu: int
    link_connected: bool
    interface_speed: int
    enabled: bool
    link_speed: int
    sriov_max_vf: int
    links: list[LinkResponse] = Field(default_factory=list)

    class Config:
        arbitrary_types_allowed = True


class InterfaceListResponse(PaginatedResponse[InterfaceResponse]):
    kind = "InterfaceList"
