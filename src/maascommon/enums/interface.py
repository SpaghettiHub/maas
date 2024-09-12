#  Copyright 2024 Canonical Ltd.  This software is licensed under the
#  GNU Affero General Public License version 3 (see the file LICENSE).

from collections import OrderedDict
from enum import Enum


class INTERFACE_TYPE(str, Enum):
    """The vocabulary of possible types for `Interface`."""

    # Note: when these constants are changed, the custom SQL query
    # in StaticIPAddressManager.get_hostname_ip_mapping() must also
    # be changed.
    PHYSICAL = "physical"
    BOND = "bond"
    BRIDGE = "bridge"
    VLAN = "vlan"
    ALIAS = "alias"
    # Interface that is created when it is not linked to a node.
    UNKNOWN = "unknown"


INTERFACE_TYPE_CHOICES = (
    (INTERFACE_TYPE.PHYSICAL, "Physical interface"),
    (INTERFACE_TYPE.BOND, "Bond"),
    (INTERFACE_TYPE.BRIDGE, "Bridge"),
    (INTERFACE_TYPE.VLAN, "VLAN interface"),
    (INTERFACE_TYPE.ALIAS, "Alias"),
    (INTERFACE_TYPE.UNKNOWN, "Unknown"),
)
INTERFACE_TYPE_CHOICES_DICT = OrderedDict(INTERFACE_TYPE_CHOICES)


class INTERFACE_LINK_TYPE(str, Enum):
    """The vocabulary of possible types to link a `Subnet` to a `Interface`."""

    AUTO = "auto"
    DHCP = "dhcp"
    STATIC = "static"
    LINK_UP = "link_up"


INTERFACE_LINK_TYPE_CHOICES = (
    (INTERFACE_LINK_TYPE.AUTO, "Auto IP"),
    (INTERFACE_LINK_TYPE.DHCP, "DHCP"),
    (INTERFACE_LINK_TYPE.STATIC, "Static IP"),
    (INTERFACE_LINK_TYPE.LINK_UP, "Link up"),
)


class BOND_MODE(str, Enum):
    BALANCE_RR = "balance-rr"
    ACTIVE_BACKUP = "active-backup"
    BALANCE_XOR = "balance-xor"
    BROADCAST = "broadcast"
    LINK_AGGREGATION = "802.3ad"
    BALANCE_TLB = "balance-tlb"
    BALANCE_ALB = "balance-alb"


BOND_MODE_CHOICES = (
    (BOND_MODE.BALANCE_RR, BOND_MODE.BALANCE_RR),
    (BOND_MODE.ACTIVE_BACKUP, BOND_MODE.ACTIVE_BACKUP),
    (BOND_MODE.BALANCE_XOR, BOND_MODE.BALANCE_XOR),
    (BOND_MODE.BROADCAST, BOND_MODE.BROADCAST),
    (BOND_MODE.LINK_AGGREGATION, BOND_MODE.LINK_AGGREGATION),
    (BOND_MODE.BALANCE_TLB, BOND_MODE.BALANCE_TLB),
    (BOND_MODE.BALANCE_ALB, BOND_MODE.BALANCE_ALB),
)


class BOND_LACP_RATE(str, Enum):
    SLOW = "slow"
    FAST = "fast"


BOND_LACP_RATE_CHOICES = (
    (BOND_LACP_RATE.FAST, BOND_LACP_RATE.FAST),
    (BOND_LACP_RATE.SLOW, BOND_LACP_RATE.SLOW),
)


class BOND_XMIT_HASH_POLICY(str, Enum):
    LAYER2 = "layer2"
    LAYER2_3 = "layer2+3"
    LAYER3_4 = "layer3+4"
    ENCAP2_3 = "encap2+3"
    ENCAP3_4 = "encap3+4"


BOND_XMIT_HASH_POLICY_CHOICES = (
    (BOND_XMIT_HASH_POLICY.LAYER2, BOND_XMIT_HASH_POLICY.LAYER2),
    (BOND_XMIT_HASH_POLICY.LAYER2_3, BOND_XMIT_HASH_POLICY.LAYER2_3),
    (BOND_XMIT_HASH_POLICY.LAYER3_4, BOND_XMIT_HASH_POLICY.LAYER3_4),
    (BOND_XMIT_HASH_POLICY.ENCAP2_3, BOND_XMIT_HASH_POLICY.ENCAP2_3),
    (BOND_XMIT_HASH_POLICY.ENCAP3_4, BOND_XMIT_HASH_POLICY.ENCAP3_4),
)


class BRIDGE_TYPE(str, Enum):
    """A bridge type."""

    STANDARD = "standard"
    OVS = "ovs"


BRIDGE_TYPE_CHOICES = (
    (BRIDGE_TYPE.STANDARD, BRIDGE_TYPE.STANDARD),
    (BRIDGE_TYPE.OVS, BRIDGE_TYPE.OVS),
)
BRIDGE_TYPE_CHOICES_DICT = OrderedDict(BRIDGE_TYPE_CHOICES)
