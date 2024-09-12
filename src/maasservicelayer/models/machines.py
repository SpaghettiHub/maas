# Copyright 2024 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

import re
from typing import Optional

from pydantic import validator

from maascommon.enums.node import HARDWARE_TYPE, NODE_STATUS
from maascommon.enums.power_driver import PowerTypeEnum
from maasservicelayer.models.base import MaasTimestampedBaseModel

# PCIE and USB vendor and product ids are represented as a 2 byte hex string
DEVICE_ID_REGEX = re.compile(r"^[\da-f]{4}$", re.I)


class Machine(MaasTimestampedBaseModel):
    system_id: str
    description: str
    owner: Optional[str]
    cpu_speed: int
    memory: int
    osystem: str
    architecture: Optional[str]
    distro_series: str
    hwe_kernel: Optional[str]
    locked: bool
    cpu_count: int
    status: NODE_STATUS
    power_type: Optional[PowerTypeEnum]
    fqdn: str
    hostname: str


class HardwareDevice(MaasTimestampedBaseModel):
    hardware_type: HARDWARE_TYPE = HARDWARE_TYPE.NODE
    vendor_id: str
    product_id: str
    vendor_name: str
    product_name: str
    commissioning_driver: str
    bus_number: int
    device_number: int
    # numa_node_id: int
    # physical_interface_id: Optional[int]
    # physical_blockdevice_id: Optional[int]
    # node_config_id: int

    @validator("vendor_id", "product_id")
    def validate_hex_ids(cls, id):
        if not DEVICE_ID_REGEX.match(id):
            raise ValueError("Must be an 8 byte hex value")
        return id


class UsbDevice(HardwareDevice):
    pass


class PciDevice(HardwareDevice):
    pci_address: str
