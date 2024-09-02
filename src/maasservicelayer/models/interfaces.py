# Copyright 2024 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from enum import Enum
from ipaddress import IPv6Address, IPv4Address
from typing import Optional, Union

from pydantic import BaseModel, Field

from maasservicelayer.models.base import MaasTimestampedBaseModel

from maasserver.enum import INTERFACE_LINK_TYPE, IPADDRESS_TYPE, INTERFACE_LINK_TYPE_CHOICES, INTERFACE_TYPE_CHOICES

InterfaceTypeEnum = Enum(
    "InterfaceType",
    dict({str(name).lower(): str(name) for name, _ in INTERFACE_TYPE_CHOICES}),
)
LinkModeEnum = Enum(
    "IpMode",
    dict({str(name): str(name) for name, _ in INTERFACE_LINK_TYPE_CHOICES}),
)

IpAddress = Union[IPv4Address, IPv6Address]

class Link(BaseModel):
    id: int
    ip_type: int
    ip_address: Optional[IpAddress]
    ip_subnet: int

    # derived from StaticIPAddress.get_interface_link_type
    @property
    def mode(self) -> LinkModeEnum:
        match self.ip_type:
            case IPADDRESS_TYPE.AUTO:
                mode = INTERFACE_LINK_TYPE.AUTO
            case IPADDRESS_TYPE.STICKY:
                mode = (
                    INTERFACE_LINK_TYPE.STATIC
                    if self.ip_address is None
                    else INTERFACE_LINK_TYPE.LINK_UP
                )
            case IPADDRESS_TYPE.USER_RESERVED:
                mode = INTERFACE_LINK_TYPE.STATIC
            case IPADDRESS_TYPE.DHCP:
                mode = INTERFACE_LINK_TYPE.DHCP
            case IPADDRESS_TYPE.DISCOVERED:
                mode = INTERFACE_LINK_TYPE.DHCP
        return LinkModeEnum(mode)

    class Config:
        arbitrary_types_allowed = True


class Interface(MaasTimestampedBaseModel):
    name: str
    type: InterfaceTypeEnum
    mac_address: Optional[str]
    # TODO
    # effective_mtu: int = 0
    link_connected: bool = True
    interface_speed: int = 0
    enabled: bool = True
    link_speed: int = 0
    sriov_max_vf: int = 0
    links: list[Link] = Field(default_factory=list)

    class Config:
        arbitrary_types_allowed = True
