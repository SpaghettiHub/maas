#  Copyright 2024 Canonical Ltd.  This software is licensed under the
#  GNU Affero General Public License version 3 (see the file LICENSE).

import pytest

from maascommon.enums.bmc import BmcTypeEnum
from maascommon.enums.interface import InterfaceLinkTypeEnum
from maascommon.enums.ipaddress import IpAddressTypeEnum
from maascommon.enums.node import (
    NodeDeviceBusEnum,
    NodeStatusEnum,
    NodeTypeEnum,
    SimplifiedNodeStatusEnum,
)
from maascommon.enums.subnet import RdnsModeEnum
from maasserver.enum import (
    BMC_TYPE,
    INTERFACE_LINK_TYPE,
    INTERFACE_TYPE,
    IPADDRESS_TYPE,
    NODE_DEVICE_BUS,
    NODE_STATUS,
    NODE_TYPE,
    RDNS_MODE,
    SIMPLIFIED_NODE_STATUS,
)
from maasservicelayer.models.interfaces import InterfaceTypeEnum


class TestEnumsSync:
    @pytest.mark.parametrize(
        "legacy_class, enum_class",
        [
            # When you migrate an enum, you MUST add it here!
            (BMC_TYPE, BmcTypeEnum),
            (INTERFACE_LINK_TYPE, InterfaceLinkTypeEnum),
            (INTERFACE_TYPE, InterfaceTypeEnum),
            (IPADDRESS_TYPE, IpAddressTypeEnum),
            (NODE_DEVICE_BUS, NodeDeviceBusEnum),
            (NODE_STATUS, NodeStatusEnum),
            (NODE_TYPE, NodeTypeEnum),
            (RDNS_MODE, RdnsModeEnum),
            (SIMPLIFIED_NODE_STATUS, SimplifiedNodeStatusEnum),
        ],
    )
    def test_enum_sync(self, legacy_class, enum_class):
        expected_pairs = enum_class.__members__.items()
        legacy_keys = [a for a in dir(legacy_class) if not a.startswith("_")]

        assert len(expected_pairs) == len(
            legacy_keys
        ), f"Mismatch in the number of members: {len(expected_pairs)} in enum, {len(legacy_keys)} in legacy class"

        for expected_key, expected_value in expected_pairs:
            assert hasattr(
                legacy_class, expected_key
            ), f"{expected_key} is missing in {legacy_class.__name__}"
            assert (
                getattr(legacy_class, expected_key) == expected_value.value
            ), (
                f"Mismatch for {expected_key}: expected {expected_value.value}, "
                f"got {getattr(legacy_class, expected_key)}"
            )
