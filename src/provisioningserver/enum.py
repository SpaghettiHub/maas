# Copyright 2018 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Enumerations meaningful to the rack contoller (and possibly the region)."""
from typing import Callable, cast

from maascommon.enums.base import enum_choices


class CONTROLLER_INSTALL_TYPE:
    """MAAS controller install type."""

    UNKNOWN = ""
    SNAP = "snap"
    DEB = "deb"


CONTROLLER_INSTALL_TYPE_CHOICES = enum_choices(CONTROLLER_INSTALL_TYPE)


class MACVLAN_MODE:
    BRIDGE = "bridge"
    PASSTHRU = "passthru"
    PRIVATE = "private"
    VEPA = "vepa"


MACVLAN_MODE_CHOICES = enum_choices(MACVLAN_MODE)


class LIBVIRT_NETWORK:
    DEFAULT = "default"
    MAAS = "maas"


LIBVIRT_NETWORK_CHOICES = enum_choices(LIBVIRT_NETWORK)


class POWER_STATE:
    ON = "on"  # Node is on
    OFF = "off"  # Node is off
    UNKNOWN = "unknown"  # Node power state is unknown
    ERROR = "error"  # Error getting the node power state


POWER_STATE_CHOICES = enum_choices(
    POWER_STATE, transform=cast(Callable[[str], str], str.capitalize)
)
