# Copyright 2024 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from typing import Optional

from pydantic import BaseModel, Field, IPvAnyAddress

from maascommon.enums.interface import INTERFACE_LINK_TYPE, INTERFACE_TYPE
from maascommon.enums.ipaddress import IPADDRESS_TYPE
from maasservicelayer.models.base import MaasTimestampedBaseModel


class Link(BaseModel):
    id: int
    ip_type: IPADDRESS_TYPE
    ip_address: Optional[IPvAnyAddress]
    ip_subnet: int

    # derived from StaticIPAddress.get_interface_link_type
    @property
    def mode(self) -> INTERFACE_LINK_TYPE:
        match self.ip_type:
            case IPADDRESS_TYPE.AUTO:
                return INTERFACE_LINK_TYPE.AUTO
            case IPADDRESS_TYPE.STICKY:
                return (
                    INTERFACE_LINK_TYPE.STATIC
                    if self.ip_address is None
                    else INTERFACE_LINK_TYPE.LINK_UP
                )
            case IPADDRESS_TYPE.USER_RESERVED:
                return INTERFACE_LINK_TYPE.STATIC
            case IPADDRESS_TYPE.DHCP:
                return INTERFACE_LINK_TYPE.DHCP
            case IPADDRESS_TYPE.DISCOVERED:
                return INTERFACE_LINK_TYPE.DHCP

    class Config:
        arbitrary_types_allowed = True


class Interface(MaasTimestampedBaseModel):
    name: str
    type: INTERFACE_TYPE
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
