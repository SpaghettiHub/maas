#  Copyright 2024 Canonical Ltd.  This software is licensed under the
#  GNU Affero General Public License version 3 (see the file LICENSE).

from collections import OrderedDict
from enum import Enum

from maascommon.enums.base import enum_choices


# Labels are also used for autotagging scripts.
class HARDWARE_TYPE(int, Enum):
    NODE = 0
    CPU = 1
    MEMORY = 2
    STORAGE = 3
    NETWORK = 4
    GPU = 5


HARDWARE_TYPE_CHOICES = (
    (HARDWARE_TYPE.NODE, "Node"),
    (HARDWARE_TYPE.CPU, "CPU"),
    (HARDWARE_TYPE.MEMORY, "Memory"),
    (HARDWARE_TYPE.STORAGE, "Storage"),
    (HARDWARE_TYPE.NETWORK, "Network"),
    (HARDWARE_TYPE.GPU, "GPU"),
)


class NODE_STATUS(int, Enum):
    """The vocabulary of a `Node`'s possible statuses."""

    # A node starts out as NEW (DEFAULT is an alias for NEW).
    DEFAULT = 0
    # The node has been created and has a system ID assigned to it.
    NEW = 0
    # Testing and other commissioning steps are taking place.
    COMMISSIONING = 1
    # The commissioning step failed.
    FAILED_COMMISSIONING = 2
    # The node can't be contacted.
    MISSING = 3
    # The node is in the general pool ready to be deployed.
    READY = 4
    # The node is ready for named deployment.
    RESERVED = 5
    # The node has booted into the operating system of its owner's choice
    # and is ready for use.
    DEPLOYED = 6
    # The node has been removed from service manually until an admin
    # overrides the retirement.
    RETIRED = 7
    # The node is broken: a step in the node lifecyle failed.
    # More details can be found in the node's event log.
    BROKEN = 8
    # The node is being installed.
    DEPLOYING = 9
    # The node has been allocated to a user and is ready for deployment.
    ALLOCATED = 10
    # The deployment of the node failed.
    FAILED_DEPLOYMENT = 11
    # The node is powering down after a release request.
    RELEASING = 12
    # The releasing of the node failed.
    FAILED_RELEASING = 13
    # The node is erasing its disks.
    DISK_ERASING = 14
    # The node failed to erase its disks.
    FAILED_DISK_ERASING = 15
    # The node is in rescue mode.
    RESCUE_MODE = 16
    # The node is entering rescue mode.
    ENTERING_RESCUE_MODE = 17
    # The node failed to enter rescue mode.
    FAILED_ENTERING_RESCUE_MODE = 18
    # The node is exiting rescue mode.
    EXITING_RESCUE_MODE = 19
    # The node failed to exit rescue mode.
    FAILED_EXITING_RESCUE_MODE = 20
    # Running tests on Node
    TESTING = 21
    # Testing has failed
    FAILED_TESTING = 22


# Django choices for NODE_STATUS: sequence of tuples (key, UI
# representation).
NODE_STATUS_CHOICES = (
    (NODE_STATUS.NEW, "New"),
    (NODE_STATUS.COMMISSIONING, "Commissioning"),
    (NODE_STATUS.FAILED_COMMISSIONING, "Failed commissioning"),
    (NODE_STATUS.MISSING, "Missing"),
    (NODE_STATUS.READY, "Ready"),
    (NODE_STATUS.RESERVED, "Reserved"),
    (NODE_STATUS.ALLOCATED, "Allocated"),
    (NODE_STATUS.DEPLOYING, "Deploying"),
    (NODE_STATUS.DEPLOYED, "Deployed"),
    (NODE_STATUS.RETIRED, "Retired"),
    (NODE_STATUS.BROKEN, "Broken"),
    (NODE_STATUS.FAILED_DEPLOYMENT, "Failed deployment"),
    (NODE_STATUS.RELEASING, "Releasing"),
    (NODE_STATUS.FAILED_RELEASING, "Releasing failed"),
    (NODE_STATUS.DISK_ERASING, "Disk erasing"),
    (NODE_STATUS.FAILED_DISK_ERASING, "Failed disk erasing"),
    (NODE_STATUS.RESCUE_MODE, "Rescue mode"),
    (NODE_STATUS.ENTERING_RESCUE_MODE, "Entering rescue mode"),
    (NODE_STATUS.FAILED_ENTERING_RESCUE_MODE, "Failed to enter rescue mode"),
    (NODE_STATUS.EXITING_RESCUE_MODE, "Exiting rescue mode"),
    (NODE_STATUS.FAILED_EXITING_RESCUE_MODE, "Failed to exit rescue mode"),
    (NODE_STATUS.TESTING, "Testing"),
    (NODE_STATUS.FAILED_TESTING, "Failed testing"),
)

# A version of NODE_STATUS_CHOICES with one-word labels
NODE_STATUS_SHORT_LABEL_CHOICES = tuple(
    sorted(
        (attr.lower(), attr.lower())
        for attr, _ in NODE_STATUS.__members__.items()
        if not attr.startswith("_") and attr != "DEFAULT"
    )
)

NODE_STATUS_CHOICES_DICT = OrderedDict(NODE_STATUS_CHOICES)


class NODE_TYPE:
    """Valid node types."""

    DEFAULT = 0
    MACHINE = 0
    DEVICE = 1
    RACK_CONTROLLER = 2
    REGION_CONTROLLER = 3
    REGION_AND_RACK_CONTROLLER = 4


# This is copied in static/js/angular/controllers/subnet_details.js. If you
# update any choices you also need to update the controller.
NODE_TYPE_CHOICES = (
    (NODE_TYPE.MACHINE, "Machine"),
    (NODE_TYPE.DEVICE, "Device"),
    (NODE_TYPE.RACK_CONTROLLER, "Rack controller"),
    (NODE_TYPE.REGION_CONTROLLER, "Region controller"),
    (NODE_TYPE.REGION_AND_RACK_CONTROLLER, "Region and rack controller"),
)

NODE_TYPE_CHOICES_DICT = OrderedDict(NODE_TYPE_CHOICES)

# NODE_STATUS when the node is owned by an owner and it is not commissioning.
ALLOCATED_NODE_STATUSES = frozenset(
    [
        NODE_STATUS.ALLOCATED,
        NODE_STATUS.DEPLOYING,
        NODE_STATUS.DEPLOYED,
        NODE_STATUS.FAILED_DEPLOYMENT,
        NODE_STATUS.RELEASING,
        NODE_STATUS.FAILED_RELEASING,
        NODE_STATUS.DISK_ERASING,
        NODE_STATUS.FAILED_DISK_ERASING,
        NODE_STATUS.RESCUE_MODE,
        NODE_STATUS.ENTERING_RESCUE_MODE,
        NODE_STATUS.FAILED_ENTERING_RESCUE_MODE,
        NODE_STATUS.EXITING_RESCUE_MODE,
        NODE_STATUS.FAILED_EXITING_RESCUE_MODE,
        NODE_STATUS.TESTING,
        NODE_STATUS.FAILED_TESTING,
    ]
)


class SIMPLIFIED_NODE_STATUS:
    """The vocabulary of a `Node`'s possible simplified statuses."""

    ALLOCATED = "Allocated"
    BROKEN = "Broken"
    COMMISSIONING = "Commissioning"
    DEPLOYED = "Deployed"
    DEPLOYING = "Deploying"
    FAILED = "Failed"
    NEW = "New"
    READY = "Ready"
    RELEASING = "Releasing"
    RESCUE_MODE = "Rescue Mode"
    TESTING = "Testing"
    OTHER = "Other"


SIMPLIFIED_NODE_STATUS_CHOICES = enum_choices(SIMPLIFIED_NODE_STATUS)

SIMPLIFIED_NODE_STATUS_CHOICES_DICT = OrderedDict(
    SIMPLIFIED_NODE_STATUS_CHOICES
)

# A version of SIMPLIFIED_NODE_STATUS_CHOICES with one-word labels
SIMPLIFIED_NODE_STATUS_LABEL_CHOICES = tuple(
    sorted(
        (attr.lower(), attr.lower())
        for attr in dir(SIMPLIFIED_NODE_STATUS)
        if not attr.startswith("_") and attr != "DEFAULT"
    )
)

SIMPLIFIED_NODE_STATUSES_MAP = {
    SIMPLIFIED_NODE_STATUS.ALLOCATED: [NODE_STATUS.ALLOCATED],
    SIMPLIFIED_NODE_STATUS.BROKEN: [NODE_STATUS.BROKEN],
    SIMPLIFIED_NODE_STATUS.COMMISSIONING: [NODE_STATUS.COMMISSIONING],
    SIMPLIFIED_NODE_STATUS.DEPLOYED: [NODE_STATUS.DEPLOYED],
    SIMPLIFIED_NODE_STATUS.DEPLOYING: [NODE_STATUS.DEPLOYING],
    SIMPLIFIED_NODE_STATUS.FAILED: [
        NODE_STATUS.FAILED_COMMISSIONING,
        NODE_STATUS.FAILED_DEPLOYMENT,
        NODE_STATUS.FAILED_DISK_ERASING,
        NODE_STATUS.FAILED_ENTERING_RESCUE_MODE,
        NODE_STATUS.FAILED_EXITING_RESCUE_MODE,
        NODE_STATUS.FAILED_RELEASING,
        NODE_STATUS.FAILED_TESTING,
    ],
    SIMPLIFIED_NODE_STATUS.NEW: [NODE_STATUS.NEW],
    SIMPLIFIED_NODE_STATUS.READY: [NODE_STATUS.READY],
    SIMPLIFIED_NODE_STATUS.RELEASING: [
        NODE_STATUS.DISK_ERASING,
        NODE_STATUS.RELEASING,
    ],
    SIMPLIFIED_NODE_STATUS.RESCUE_MODE: [
        NODE_STATUS.ENTERING_RESCUE_MODE,
        NODE_STATUS.EXITING_RESCUE_MODE,
        NODE_STATUS.RESCUE_MODE,
    ],
    SIMPLIFIED_NODE_STATUS.TESTING: [NODE_STATUS.TESTING],
}

SIMPLIFIED_NODE_STATUSES_MAP_REVERSED = {
    val: simple_status
    for simple_status, values in SIMPLIFIED_NODE_STATUSES_MAP.items()
    for val in values
}


class NODE_DEVICE_BUS:
    PCIE = 1
    USB = 2


NODE_DEVICE_BUS_CHOICES = (
    (NODE_DEVICE_BUS.PCIE, "PCIE"),
    (NODE_DEVICE_BUS.USB, "USB"),
)
NODE_TYPE_TO_LINK_TYPE = {
    NODE_TYPE.DEVICE: "device",
    NODE_TYPE.MACHINE: "machine",
    NODE_TYPE.RACK_CONTROLLER: "controller",
    NODE_TYPE.REGION_CONTROLLER: "controller",
    NODE_TYPE.REGION_AND_RACK_CONTROLLER: "controller",
}
