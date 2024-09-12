# Copyright 2012-2020 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Enumerations meaningful to the maasserver application."""

__all__ = [
    "CACHE_MODE_TYPE",
    "CACHE_MODE_TYPE_CHOICES",
    "COMPONENT",
    "DEVICE_IP_ASSIGNMENT_TYPE",
    "FILESYSTEM_GROUP_TYPE",
    "FILESYSTEM_GROUP_TYPE_CHOICES",
    "FILESYSTEM_TYPE",
    "FILESYSTEM_TYPE_CHOICES",
    "PARTITION_TABLE_TYPE",
    "PARTITION_TABLE_TYPE_CHOICES",
    "PRESEED_TYPE",
    "RDNS_MODE",
    "RDNS_MODE_CHOICES",
    "RDNS_MODE_CHOICES_DICT",
    "KEYS_PROTOCOL_TYPE",
    "KEYS_PROTOCOL_TYPE_CHOICES",
]

from collections import OrderedDict
from typing import Callable, cast

from maascommon.enums.base import enum_choices


class COMPONENT:
    """Major moving parts of the application that may have failure states."""

    PSERV = "provisioning server"
    IMPORT_PXE_FILES = "maas-import-pxe-files script"
    RACK_CONTROLLERS = "clusters"
    REGION_IMAGE_IMPORT = "Image importer"
    REGION_IMAGE_SYNC = "Image synchronization"
    REGION_IMAGE_DB_EXPORT = "bootresources_export_from_db"


class NODE_ACTION_TYPE:
    """Types of action a node can have done."""

    LIFECYCLE = "lifecycle"
    POWER = "power"
    TESTING = "testing"
    LOCK = "lock"
    MISC = "misc"


class DEVICE_IP_ASSIGNMENT_TYPE:
    """The vocabulary of a `Device`'s possible IP assignment type. This value
    is calculated by looking at the overall model for a `Device`. This is not
    set directly on the model."""

    # Device is outside of MAAS control.
    EXTERNAL = "external"

    # Device receives ip address from the appropriate dynamic range.
    DYNAMIC = "dynamic"

    # Device has ip address assigned from some appropriate subnet.
    STATIC = "static"


class PRESEED_TYPE:
    """Types of preseed documents that can be generated."""

    COMMISSIONING = "commissioning"
    ENLIST = "enlist"
    CURTIN = "curtin"


class RDNS_MODE:
    """The vocabulary of a `Subnet`'s possible reverse DNS modes."""

    # By default, we do what we've always done: assume we rule the DNS world.
    DEFAULT = 2
    # Do not generate reverse DNS for this Subnet.
    DISABLED = 0
    # Generate reverse DNS only for the CIDR.
    ENABLED = 1
    # Generate RFC2317 glue if needed (Subnet is too small for its own zone.)
    RFC2317 = 2


# Django choices for RDNS_MODE: sequence of tuples (key, UI representation.)
RDNS_MODE_CHOICES = (
    (RDNS_MODE.DISABLED, "Disabled"),
    (RDNS_MODE.ENABLED, "Enabled"),
    (RDNS_MODE.RFC2317, "Enabled, with rfc2317 glue zone."),
)


RDNS_MODE_CHOICES_DICT = OrderedDict(RDNS_MODE_CHOICES)


class IPRANGE_TYPE:
    """The vocabulary of possible types of `IPRange` objects."""

    # Dynamic IP Range.
    DYNAMIC = "dynamic"

    # Reserved for exclusive use by MAAS (and possibly a particular user).
    RESERVED = "reserved"


IPRANGE_TYPE_CHOICES = (
    (IPRANGE_TYPE.DYNAMIC, "Dynamic IP Range"),
    (IPRANGE_TYPE.RESERVED, "Reserved IP Range"),
)


class POWER_WORKFLOW_ACTIONS:
    # Temporal parameter to execute a workflow for powering on
    # a machine
    ON = "power_on"

    # Temporal parameter to execute a workflow for powering on
    # a machine
    OFF = "power_off"

    # Temporal parameter to execute a workflow for powering on
    # a machine
    CYCLE = "power_cycle"

    # Temporal parameter to execute a workflow for powering on
    # a machine
    QUERY = "power_query"


class DEPLOYMENT_TARGET:
    # A node has been deployed ephemerally
    MEMORY = "memory"

    DISK = "disk"


DEPLOYMENT_TARGET_CHOICES = enum_choices(
    DEPLOYMENT_TARGET, transform=cast(Callable[[str], str], str.capitalize)
)


class BOOT_RESOURCE_TYPE:
    """Possible types for `BootResource`."""

    SYNCED = 0  # downloaded from BootSources
    # index 1 was GENERATED, now unused
    UPLOADED = 2  # uploaded by user


# Django choices for BOOT_RESOURCE_TYPE: sequence of tuples (key, UI
# representation).
BOOT_RESOURCE_TYPE_CHOICES = (
    (BOOT_RESOURCE_TYPE.SYNCED, "Synced"),
    (BOOT_RESOURCE_TYPE.UPLOADED, "Uploaded"),
)


BOOT_RESOURCE_TYPE_CHOICES_DICT = OrderedDict(BOOT_RESOURCE_TYPE_CHOICES)


class BOOT_RESOURCE_FILE_TYPE:
    """The vocabulary of possible file types for `BootResource`."""

    # Tarball of root image.
    ROOT_TGZ = "root-tgz"
    ROOT_TBZ = "root-tbz"
    ROOT_TXZ = "root-txz"

    # Tarball of dd image.
    ROOT_DD = "root-dd"
    ROOT_DDTAR = "root-dd.tar"

    # Raw dd image
    ROOT_DDRAW = "root-dd.raw"

    # Compressed dd image types
    ROOT_DDBZ2 = "root-dd.bz2"
    ROOT_DDGZ = "root-dd.gz"
    ROOT_DDXZ = "root-dd.xz"

    # Compressed tarballs of dd images
    ROOT_DDTBZ = "root-dd.tar.bz2"
    ROOT_DDTXZ = "root-dd.tar.xz"
    # For backwards compatibility, DDTGZ files are named root-dd
    ROOT_DDTGZ = "root-dd"

    # Following are not allowed on user upload. Only used for syncing
    # from another simplestreams source. (Most likely images.maas.io)

    # Root Image (gets converted to root-image root-tgz, on the rack)
    ROOT_IMAGE = "root-image.gz"

    # Root image in SquashFS form, does not need to be converted
    SQUASHFS_IMAGE = "squashfs"

    # Boot Kernel
    BOOT_KERNEL = "boot-kernel"

    # Boot Initrd
    BOOT_INITRD = "boot-initrd"

    # Boot DTB
    BOOT_DTB = "boot-dtb"

    # tar.xz of files which need to be extracted so the files are usable
    # by MAAS
    ARCHIVE_TAR_XZ = "archive.tar.xz"


# Django choices for BOOT_RESOURCE_FILE_TYPE: sequence of tuples (key, UI
# representation).
BOOT_RESOURCE_FILE_TYPE_CHOICES = (
    (BOOT_RESOURCE_FILE_TYPE.ROOT_TGZ, "Root Image (tar.gz)"),
    (BOOT_RESOURCE_FILE_TYPE.ROOT_TBZ, "Root Image (tar.bz2)"),
    (BOOT_RESOURCE_FILE_TYPE.ROOT_TXZ, "Root image (tar.xz)"),
    (BOOT_RESOURCE_FILE_TYPE.ROOT_DD, "Root Compressed DD (dd -> tar.gz)"),
    (BOOT_RESOURCE_FILE_TYPE.ROOT_DDTGZ, "Root Compressed DD (dd -> tar.gz)"),
    (
        BOOT_RESOURCE_FILE_TYPE.ROOT_DDTAR,
        "Root Tarfile with DD (dd -> root-dd.tar)",
    ),
    (
        BOOT_RESOURCE_FILE_TYPE.ROOT_DDRAW,
        "Raw root DD image(dd -> root-dd.raw)",
    ),
    (
        BOOT_RESOURCE_FILE_TYPE.ROOT_DDTBZ,
        "Root Compressed DD (dd -> root-dd.tar.bz2)",
    ),
    (
        BOOT_RESOURCE_FILE_TYPE.ROOT_DDTXZ,
        "Root Compressed DD (dd -> root-dd.tar.xz)",
    ),
    (BOOT_RESOURCE_FILE_TYPE.ROOT_DDBZ2, "Root Compressed DD (root-dd.bz2)"),
    (BOOT_RESOURCE_FILE_TYPE.ROOT_DDGZ, "Root Compressed DD (root-dd.gz)"),
    (BOOT_RESOURCE_FILE_TYPE.ROOT_DDXZ, "Root Compressed DD (root-dd.xz)"),
    (BOOT_RESOURCE_FILE_TYPE.ROOT_IMAGE, "Compressed Root Image"),
    (BOOT_RESOURCE_FILE_TYPE.SQUASHFS_IMAGE, "SquashFS Root Image"),
    (BOOT_RESOURCE_FILE_TYPE.BOOT_KERNEL, "Linux ISCSI Kernel"),
    (BOOT_RESOURCE_FILE_TYPE.BOOT_INITRD, "Initial ISCSI Ramdisk"),
    (BOOT_RESOURCE_FILE_TYPE.BOOT_DTB, "ISCSI Device Tree Blob"),
    (BOOT_RESOURCE_FILE_TYPE.ARCHIVE_TAR_XZ, "Archives.tar.xz set of files"),
)


class PARTITION_TABLE_TYPE:
    """The vocabulary of possible partition types for `PartitionTable`."""

    # GUID partition table.
    GPT = "GPT"

    # Master boot record..
    MBR = "MBR"


# Django choices for PARTITION_TABLE_TYPE: sequence of tuples (key, UI
# representation).
PARTITION_TABLE_TYPE_CHOICES = (
    (PARTITION_TABLE_TYPE.MBR, "Master boot record"),
    (PARTITION_TABLE_TYPE.GPT, "GUID parition table"),
)


class FILESYSTEM_TYPE:
    """The vocabulary of possible partition types for `Filesystem`."""

    # Second extended filesystem.
    EXT2 = "ext2"

    # Fourth extended filesystem.
    EXT4 = "ext4"

    # XFS
    XFS = "xfs"

    # FAT32
    FAT32 = "fat32"

    # VFAT
    VFAT = "vfat"

    # LVM Physical Volume.
    LVM_PV = "lvm-pv"

    # RAID.
    RAID = "raid"

    # RAID spare.
    RAID_SPARE = "raid-spare"

    # Bcache cache.
    BCACHE_CACHE = "bcache-cache"

    # Bcache backing.
    BCACHE_BACKING = "bcache-backing"

    # Swap
    SWAP = "swap"

    # RAMFS. Note that tmpfs provides a superset of ramfs's features and can
    # be safer.
    RAMFS = "ramfs"

    # TMPFS
    TMPFS = "tmpfs"

    # BTRFS
    BTRFS = "btrfs"

    # ZFS
    ZFSROOT = "zfsroot"

    # VMFS6
    VMFS6 = "vmfs6"


# Django choices for FILESYSTEM_TYPE: sequence of tuples (key, UI
# representation).
FILESYSTEM_TYPE_CHOICES = (
    (FILESYSTEM_TYPE.EXT2, "ext2"),
    (FILESYSTEM_TYPE.EXT4, "ext4"),
    # XFS, FAT32, and VFAT are typically written all-caps. However, the UI/UX
    # team want them displayed lower-case to fit with the style guidelines.
    (FILESYSTEM_TYPE.XFS, "xfs"),
    (FILESYSTEM_TYPE.FAT32, "fat32"),
    (FILESYSTEM_TYPE.VFAT, "vfat"),
    (FILESYSTEM_TYPE.LVM_PV, "lvm"),
    (FILESYSTEM_TYPE.RAID, "raid"),
    (FILESYSTEM_TYPE.RAID_SPARE, "raid-spare"),
    (FILESYSTEM_TYPE.BCACHE_CACHE, "bcache-cache"),
    (FILESYSTEM_TYPE.BCACHE_BACKING, "bcache-backing"),
    (FILESYSTEM_TYPE.SWAP, "swap"),
    (FILESYSTEM_TYPE.RAMFS, "ramfs"),
    (FILESYSTEM_TYPE.TMPFS, "tmpfs"),
    (FILESYSTEM_TYPE.BTRFS, "btrfs"),
    (FILESYSTEM_TYPE.ZFSROOT, "zfsroot"),
    (FILESYSTEM_TYPE.VMFS6, "vmfs6"),
)


# Django choices for FILESYSTEM_TYPE: sequence of tuples (key, UI
# representation). When a user does a format operation only these values
# are allowed. The other values are reserved for internal use.
FILESYSTEM_FORMAT_TYPE_CHOICES = (
    (FILESYSTEM_TYPE.EXT2, "ext2"),
    (FILESYSTEM_TYPE.EXT4, "ext4"),
    # XFS, FAT32, and VFAT are typically written all-caps. However, the UI/UX
    # team want them displayed lower-case to fit with the style guidelines.
    (FILESYSTEM_TYPE.XFS, "xfs"),
    (FILESYSTEM_TYPE.FAT32, "fat32"),
    (FILESYSTEM_TYPE.VFAT, "vfat"),
    (FILESYSTEM_TYPE.SWAP, "swap"),
    (FILESYSTEM_TYPE.RAMFS, "ramfs"),
    (FILESYSTEM_TYPE.TMPFS, "tmpfs"),
    (FILESYSTEM_TYPE.BTRFS, "btrfs"),
    (FILESYSTEM_TYPE.ZFSROOT, "zfsroot"),
)


FILESYSTEM_FORMAT_TYPE_CHOICES_DICT = OrderedDict(
    FILESYSTEM_FORMAT_TYPE_CHOICES
)


class FILESYSTEM_GROUP_TYPE:
    """The vocabulary of possible partition types for `FilesystemGroup`."""

    # LVM volume group.
    LVM_VG = "lvm-vg"

    # RAID level 0
    RAID_0 = "raid-0"

    # RAID level 1
    RAID_1 = "raid-1"

    # RAID level 5
    RAID_5 = "raid-5"

    # RAID level 6
    RAID_6 = "raid-6"

    # RAID level 10
    RAID_10 = "raid-10"

    # Bcache
    BCACHE = "bcache"

    # VMFS6
    VMFS6 = "vmfs6"


FILESYSTEM_GROUP_RAID_TYPES = [
    FILESYSTEM_GROUP_TYPE.RAID_0,
    FILESYSTEM_GROUP_TYPE.RAID_1,
    FILESYSTEM_GROUP_TYPE.RAID_5,
    FILESYSTEM_GROUP_TYPE.RAID_6,
    FILESYSTEM_GROUP_TYPE.RAID_10,
]

# Django choices for FILESYSTEM_GROUP_RAID_TYPES: sequence of tuples (key, UI
# representation).
FILESYSTEM_GROUP_RAID_TYPE_CHOICES = (
    (FILESYSTEM_GROUP_TYPE.RAID_0, "RAID 0"),
    (FILESYSTEM_GROUP_TYPE.RAID_1, "RAID 1"),
    (FILESYSTEM_GROUP_TYPE.RAID_5, "RAID 5"),
    (FILESYSTEM_GROUP_TYPE.RAID_6, "RAID 6"),
    (FILESYSTEM_GROUP_TYPE.RAID_10, "RAID 10"),
)

# Django choices for FILESYSTEM_GROUP_TYPE: sequence of tuples (key, UI
# representation).
FILESYSTEM_GROUP_TYPE_CHOICES = FILESYSTEM_GROUP_RAID_TYPE_CHOICES + (
    (FILESYSTEM_GROUP_TYPE.LVM_VG, "LVM VG"),
    (FILESYSTEM_GROUP_TYPE.BCACHE, "Bcache"),
    (FILESYSTEM_GROUP_TYPE.VMFS6, "VMFS6"),
)


class CACHE_MODE_TYPE:
    """The vocabulary of possible types of cache."""

    WRITEBACK = "writeback"
    WRITETHROUGH = "writethrough"
    WRITEAROUND = "writearound"


# Django choices for CACHE_MODE_TYPE: sequence of tuples (key, UI
# representation).
CACHE_MODE_TYPE_CHOICES = enum_choices(
    CACHE_MODE_TYPE, transform=cast(Callable[[str], str], str.capitalize)
)


class SERVICE_STATUS:
    """Service statuses"""

    # Status of the service is not known.
    UNKNOWN = "unknown"
    # Service is running and operational.
    RUNNING = "running"
    # Service is running but is in a degraded state.
    DEGRADED = "degraded"
    # Service is dead. (Should be on but is off).
    DEAD = "dead"
    # Service is off. (Should be off and is off).
    OFF = "off"


SERVICE_STATUS_CHOICES = enum_choices(
    SERVICE_STATUS, transform=cast(Callable[[str], str], str.capitalize)
)


class KEYS_PROTOCOL_TYPE:
    """The vocabulary of possible protocol types for `KeySource`."""

    # Launchpad
    LP = "lp"

    # Github
    GH = "gh"


KEYS_PROTOCOL_TYPE_CHOICES = (
    (KEYS_PROTOCOL_TYPE.LP, "launchpad"),
    (KEYS_PROTOCOL_TYPE.GH, "github"),
)


class NODE_METADATA:
    # Record metadata using a variant of SNMP OID names. See:
    #     http://www.ietf.org/rfc/rfc2737.txt
    # (eg. turn entPhysicalModelName into "physical-model-name").
    PHYSICAL_HARDWARE_REV = "physical-hardware-rev"
    PHYSICAL_MFG_NAME = "physical-mfg-name"
    PHYSICAL_MODEL_NAME = "physical-model-name"
    PHYSICAL_NAME = "physical-name"
    PHYSICAL_SERIAL_NUM = "physical-serial-num"
    VENDOR_NAME = "vendor-name"


class ENDPOINT:
    API = 0
    UI = 1
    CLI = 2


ENDPOINT_CHOICES = (
    (ENDPOINT.API, "API"),
    (ENDPOINT.UI, "WebUI"),
    (ENDPOINT.CLI, "CLI"),
)


class MSM_STATUS:
    NOT_CONNECTED = "not_connected"
    PENDING = "pending"
    CONNECTED = "connected"
