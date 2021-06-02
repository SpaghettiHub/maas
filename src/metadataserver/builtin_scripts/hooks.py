# Copyright 2012-2021 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Builtin script hooks, run upon receipt of ScriptResult"""


from collections import defaultdict
import fnmatch
from functools import partial
import json
import logging
from operator import itemgetter
import re

from django.core.exceptions import ValidationError
from django.db.models import Q

from maasserver.enum import NODE_DEVICE_BUS, NODE_METADATA, NODE_STATUS
from maasserver.models.blockdevice import MIN_BLOCK_DEVICE_SIZE
from maasserver.models.interface import Interface, PhysicalInterface
from maasserver.models.node import Node
from maasserver.models.nodedevice import NodeDevice
from maasserver.models.nodemetadata import NodeMetadata
from maasserver.models.numa import NUMANode, NUMANodeHugepages
from maasserver.models.physicalblockdevice import PhysicalBlockDevice
from maasserver.models.subnet import Subnet
from maasserver.models.tag import Tag
from maasserver.utils.orm import get_one
from maasserver.utils.osystems import get_release
from metadataserver.builtin_scripts.network import (
    is_commissioning,
    update_node_interfaces,
)
from metadataserver.enum import HARDWARE_TYPE
from provisioningserver.refresh.node_info_scripts import (
    GET_FRUID_DATA_OUTPUT_NAME,
    KERNEL_CMDLINE_OUTPUT_NAME,
    LIST_MODALIASES_OUTPUT_NAME,
    LXD_OUTPUT_NAME,
    NODE_INFO_SCRIPTS,
)
from provisioningserver.utils import kernel_to_debian_architecture
from provisioningserver.utils.lxd import parse_lxd_cpuinfo, parse_lxd_networks

logger = logging.getLogger(__name__)


SWITCH_TAG_NAME = "switch"
SWITCH_HARDWARE = [
    # Seen on Facebook Wedge 40 switch:
    #     pci:v000014E4d0000B850sv000014E4sd0000B850bc02sc00i00
    #     (Broadcom Trident II ASIC)
    {
        "modaliases": ["pci:v000014E4d0000B850sv*sd*bc*sc*i*"],
        "tag": "bcm-trident2-asic",
        "comment": 'Broadcom High-Capacity StrataXGS "Trident II" '
        "Ethernet Switch ASIC",
    },
    # Seen on Facebook Wedge 100 switch:
    #     pci:v000014E4d0000B960sv000014E4sd0000B960bc02sc00i00
    #     (Broadcom Tomahawk ASIC)
    {
        "modaliases": ["pci:v000014E4d0000B960sv*sd*bc*sc*i*"],
        "tag": "bcm-tomahawk-asic",
        "comment": 'Broadcom High-Density 25/100 StrataXGS "Tomahawk" '
        "Ethernet Switch ASIC",
    },
]


def _parse_interface_speed(port):
    supported_modes = port.get("supported_modes")
    if supported_modes is None:
        return 0

    # Return the highest supported speed.
    return max(
        int(supported_mode.split("base")[0])
        for supported_mode in supported_modes
    )


def parse_interfaces(node, data):
    """Return a dict of interfaces keyed by MAC address."""
    interfaces = {}

    resources = data["resources"]
    ifaces_info = parse_lxd_networks(data["networks"])

    def process_port(card, port):
        mac = port.get("address")

        interface = {
            "name": port.get("id"),
            "link_connected": port.get("link_detected"),
            "interface_speed": _parse_interface_speed(port),
            "link_speed": port.get("link_speed", 0),
            "numa_node": card.get("numa_node", 0),
            "vendor": card.get("vendor"),
            "product": card.get("product"),
            "firmware_version": card.get("firmware_version"),
            "sriov_max_vf": card.get("sriov", {}).get("maximum_vfs", 0),
            "pci_address": card.get("pci_address"),
            "usb_address": card.get("usb_address"),
        }
        # Assign the IP addresses to this interface
        link = ifaces_info.get(interface["name"])
        interface["ips"] = link["addresses"] if link else []

        interfaces[mac] = interface

    network_cards = resources.get("network", {}).get("cards", {})
    for card in network_cards:
        for port in card.get("ports", []):
            process_port(card, port)

        # don't sync VFs for deployed machines, MAAS has no way of representing
        # VFs, since they would persist when the machine is released and break
        # subsequent deploys.
        if node.status != NODE_STATUS.DEPLOYED:
            # entry can be present but None
            vfs = card.get("sriov", {}).get("vfs") or {}
            for vf in vfs:
                for vf_port in vf.get("ports", []):
                    process_port(vf, vf_port)

    return interfaces


def update_interface_details(interface, details):
    """Update details for an existing interface from commissioning data.

    This should be passed details from the parse_interfaces call.

    """
    iface_details = details.get(interface.mac_address)
    if not iface_details:
        return

    update_fields = []
    for field in (
        "name",
        "vendor",
        "product",
        "firmware_version",
        "link_speed",
        "interface_speed",
    ):
        value = iface_details.get(field, "")
        if getattr(interface, field) != value:
            setattr(interface, field, value)
        update_fields.append(field)

    sriov_max_vf = iface_details.get("sriov_max_vf")
    if interface.sriov_max_vf != sriov_max_vf:
        interface.sriov_max_vf = sriov_max_vf
        update_fields.append("sriov_max_vf")
    if update_fields:
        interface.save(update_fields=["updated", *update_fields])


BOOTIF_RE = re.compile(r"BOOTIF=\d\d-([0-9a-f]{2}(?:-[0-9a-f]{2}){5})")


def parse_bootif_cmdline(cmdline):
    match = BOOTIF_RE.search(cmdline)
    if match:
        return match.group(1).replace("-", ":").lower()
    return None


def update_boot_interface(node, output, exit_status):
    """Update the boot interface from the kernel command line.

    If a BOOTIF parameter is present, that's the interface the machine
    booted off.
    """
    if exit_status != 0:
        logger.error(
            "%s: kernel-cmdline failed with status: "
            "%s." % (node.hostname, exit_status)
        )
        return

    cmdline = output.decode("utf-8")
    boot_mac = parse_bootif_cmdline(cmdline)
    if boot_mac is None:
        # This is ok. For example, if a rack controller runs the
        # commissioning scripts, it won't have the BOOTIF parameter
        # there.
        return None

    try:
        node.boot_interface = node.interface_set.get(mac_address=boot_mac)
    except Interface.DoesNotExist:
        logger.error(
            f"'BOOTIF interface {boot_mac} doesn't exist for " f"{node.fqdn}"
        )
    else:
        node.save(update_fields=["boot_interface"])


def update_node_network_information(node, data, numa_nodes):
    network_devices = {}
    # Skip network configuration if set by the user.
    if node.skip_networking:
        # Turn off skip_networking now that the hook has been called.
        node.skip_networking = False
        node.save(update_fields=["skip_networking"])
        return network_devices

    update_node_interfaces(node, data)
    interfaces_info = parse_interfaces(node, data)
    current_interfaces = set()

    for mac, iface in interfaces_info.items():
        link_connected = iface.get("link_connected")
        sriov_max_vf = iface.get("sriov_max_vf")

        try:
            interface = PhysicalInterface.objects.get(mac_address=mac)
        except PhysicalInterface.DoesNotExist:
            continue
        interface.numa_node = numa_nodes[iface["numa_node"]]

        if iface.get("pci_address"):
            network_devices[iface.get("pci_address")] = interface
        elif iface.get("usb_address"):
            network_devices[iface.get("usb_address")] = interface

        current_interfaces.add(interface)
        if sriov_max_vf:
            interface.add_tag("sriov")
            interface.save(update_fields=["tags"])

        if not link_connected:
            # This interface is now disconnected.
            if interface.vlan is not None:
                interface.vlan = None
                interface.save(update_fields=["vlan", "updated"])
        interface.save()

    # If a machine boots by UUID before commissioning(s390x) no boot_interface
    # will be set as interfaces existed during boot. Set it using the
    # boot_cluster_ip now that the interfaces have been created.
    if node.boot_interface is None and node.boot_cluster_ip is not None:
        subnet = Subnet.objects.get_best_subnet_for_ip(node.boot_cluster_ip)
        if subnet:
            node.boot_interface = node.interface_set.filter(
                vlan=subnet.vlan,
            ).first()
            node.save(update_fields=["boot_interface"])

    # Pods are already deployed. MAAS captures the network state, it does
    # not change it.
    if is_commissioning(node):
        # Only configured Interfaces are tested so configuration must be done
        # before regeneration.
        node.set_initial_networking_configuration()

        # XXX ltrager 11-16-2017 - Don't regenerate ScriptResults on
        # controllers. Currently this is not needed saving us 1 database query.
        # However, if commissioning is ever enabled for controllers
        # regeneration will need to be allowed on controllers otherwise network
        # testing may break.
        if (
            node.current_testing_script_set is not None
            and not node.is_controller
        ):
            # LP: #1731353 - Regenerate ScriptResults before deleting Interfaces.
            # This creates a ScriptResult with proper parameters for each interface
            # on the system. Interfaces no long available will be deleted which
            # causes a casade delete on their assoicated ScriptResults.
            node.current_testing_script_set.regenerate(
                storage=False, network=True
            )

    return network_devices


def _process_system_information(node, system_data):
    def validate_and_set_data(key, value):
        # Some vendors use placeholders when not setting data.
        if not value or value.lower() in ["0123456789", "none"]:
            value = None
        if value:
            NodeMetadata.objects.update_or_create(
                node=node, key=key, defaults={"value": value}
            )
        else:
            NodeMetadata.objects.filter(node=node, key=key).delete()

    uuid = system_data.get("uuid")
    if not uuid or not re.search(
        r"^[\da-f]{8}[\-]?([\da-f]{4}[\-]?){3}[\da-f]{12}$", uuid, re.I
    ):
        # Convert "" to None, so that the unique check isn't triggered.
        # Some vendors store the service tag as the UUID which is not unique,
        # if the UUID isn't a valid UUID ignore it.
        node.hardware_uuid = None
    else:
        # LP:1893690 - If the UUID is valid check that it isn't duplicated
        # with save so the check is atomic.
        node.hardware_uuid = uuid
        try:
            node.save()
        except ValidationError as e:
            # Check that the ValidationError is due to the hardware_uuid
            # other errors will be caught and logged later.
            if "hardware_uuid" in e.error_dict:
                node.hardware_uuid = None
                # If the UUID isn't really unique make sure it isn't stored on
                # any Node.
                Node.objects.filter(hardware_uuid=uuid).update(
                    hardware_uuid=None
                )

    # Gather system information. Custom built machines and some Supermicro
    # servers do not provide this information.
    for i in ["vendor", "product", "family", "version", "sku", "serial"]:
        validate_and_set_data(f"system_{i}", system_data.get(i))

    # Gather mainboard information, all systems should have this.
    motherboard = system_data.get("motherboard")
    # LP:1881116 - LXD will sometimes define the value as None.
    motherboard = motherboard if isinstance(motherboard, dict) else {}
    for i in ["vendor", "product", "serial", "version"]:
        validate_and_set_data(f"mainboard_{i}", motherboard.get(i))

    # Gather mainboard firmware information.
    firmware = system_data.get("firmware")
    firmware = firmware if isinstance(firmware, dict) else {}
    for i in ["vendor", "date", "version"]:
        validate_and_set_data(f"mainboard_firmware_{i}", firmware.get(i))

    # Gather chassis information.
    chassis = system_data.get("chassis")
    chassis = chassis if isinstance(chassis, dict) else {}
    for i in ["vendor", "type", "serial", "version"]:
        validate_and_set_data(f"chassis_{i}", chassis.get(i))

    # Set the virtual tag.
    system_type = system_data.get("type")
    tag, _ = Tag.objects.get_or_create(name="virtual")
    if not system_type or system_type == "physical":
        node.tags.remove(tag)
    else:
        node.tags.add(tag)


def _add_or_update_node_device(
    node,
    numa_nodes,
    network_devices,
    storage_devices,
    gpu_devices,
    old_devices,
    bus,
    device,
    address,
    key,
    commissioning_driver,
):
    network_device = network_devices.get(address)
    storage_device = storage_devices.get(address)

    if network_device:
        hardware_type = HARDWARE_TYPE.NETWORK
    elif storage_device:
        hardware_type = HARDWARE_TYPE.STORAGE
    elif address in gpu_devices:
        hardware_type = HARDWARE_TYPE.GPU
    else:
        hardware_type = HARDWARE_TYPE.NODE

    if "numa_node" in device:
        numa_node = numa_nodes[device["numa_node"]]
    else:
        # LXD doesn't map USB devices to NUMA node nor does it map
        # USB devices to USB controller on the PCI bus. Map to the
        # default numa node in cache.
        numa_node = numa_nodes[0]

    if key in old_devices:
        node_device = old_devices.pop(key)
        node_device.hardware_type = hardware_type
        node_device.numa_node = numa_node
        node_device.physical_block_device = storage_device
        node_device.physical_interface = network_device
        node_device.vendor_name = device.get("vendor")
        node_device.product_name = device.get("product")
        node_device.commissioning_driver = commissioning_driver
        node_device.save()
    else:
        pci_address = device.get("pci_address")
        create_args = {
            "bus": bus,
            "hardware_type": hardware_type,
            "node": node,
            "numa_node": numa_node,
            "physical_blockdevice": storage_device,
            "physical_interface": network_device,
            "vendor_id": device["vendor_id"],
            "product_id": device["product_id"],
            "vendor_name": device.get("vendor"),
            "product_name": device.get("product"),
            "commissioning_driver": commissioning_driver,
            "bus_number": device.get("bus_address"),
            "device_number": device.get("device_address"),
            "pci_address": pci_address,
        }
        try:
            NodeDevice.objects.create(**create_args)
        except ValidationError:
            # A device was replaced, delete the old one before creating
            # the new one.
            qs = NodeDevice.objects.filter(node=node)
            if pci_address is not None:
                identifier = {"pci_address": pci_address}
            else:
                identifier = {
                    "bus_number": device.get("bus_address"),
                    "device_number": device.get("device_address"),
                }
            if storage_device and network_device:
                qs = qs.filter(
                    Q(**identifier)
                    | Q(physical_blockdevice=storage_device)
                    | Q(physical_interface=network_device)
                )
            elif storage_device:
                qs = qs.filter(
                    Q(**identifier) | Q(physical_blockdevice=storage_device)
                )
            elif network_device:
                qs = qs.filter(
                    Q(**identifier) | Q(physical_interface=network_device)
                )
            else:
                qs = qs.filter(**identifier)
            qs.delete()
            NodeDevice.objects.create(**create_args)


def _process_pcie_devices(add_func, data):
    for device in data.get("pci", {}).get("devices", []):
        key = (
            device["vendor_id"],
            device["product_id"],
            device["pci_address"],
        )
        add_func(
            NODE_DEVICE_BUS.PCIE,
            device,
            device["pci_address"],
            key,
            device.get("driver"),
        )


def _process_usb_devices(add_func, data):
    for device in data.get("usb", {}).get("devices", []):
        usb_address = "%s:%s" % (
            device["bus_address"],
            device["device_address"],
        )
        key = (device["vendor_id"], device["product_id"], usb_address)
        # USB devices can have different drivers for each
        # functionality. e.g a webcam has a video and audio driver.
        commissioning_driver = ", ".join(
            set(
                [
                    interface["driver"]
                    for interface in device.get("interfaces", [])
                    if "driver" in interface
                ]
            )
        )
        add_func(
            NODE_DEVICE_BUS.USB, device, usb_address, key, commissioning_driver
        )


def update_node_devices(
    node, data, numa_nodes, network_devices=None, storage_devices=None
):
    # network and storage devices are only passed if they were updated. If
    # configuration was skipped or running on a controller devices must be
    # loaded for mapping.
    if not network_devices:
        network_devices = {}
        mac_to_dev_ids = {}
        for card in data.get("network", {}).get("cards", []):
            for port in card.get("ports", []):
                if "address" not in port:
                    continue
                if "pci_address" in card:
                    mac_to_dev_ids[port["address"]] = card["pci_address"]
                elif "usb_address" in card:
                    mac_to_dev_ids[port["address"]] = card["usb_address"]
        for iface in node.interface_set.filter(
            mac_address__in=mac_to_dev_ids.keys()
        ):
            network_devices[mac_to_dev_ids[iface.mac_address]] = iface

    if not storage_devices:
        storage_devices = {}
        name_to_dev_ids = {}
        for disk in _condense_luns(data.get("storage", {}).get("disks", [])):
            if "pci_address" in disk:
                name_to_dev_ids[disk["id"]] = disk["pci_address"]
            elif "usb_address" in disk:
                name_to_dev_ids[disk["id"]] = disk["usb_address"]
        for block_dev in node.physicalblockdevice_set.filter(
            name__in=name_to_dev_ids.keys()
        ):
            storage_devices[name_to_dev_ids[block_dev.name]] = block_dev

    # Gather the list of GPUs for setting the type.
    gpu_devices = set()
    for card in data.get("gpu", {}).get("cards", []):
        if "pci_address" in card:
            gpu_devices.add(card["pci_address"])
        elif "usb_address" in card:
            gpu_devices.add(card["usb_address"])

    old_devices = {
        (
            node_device.vendor_id,
            node_device.product_id,
            node_device.pci_address
            if node_device.bus == NODE_DEVICE_BUS.PCIE
            else f"{node_device.bus_number}:{node_device.device_number}",
        ): node_device
        for node_device in node.node_devices.all()
    }

    add_func = partial(
        _add_or_update_node_device,
        node,
        numa_nodes,
        network_devices,
        storage_devices,
        gpu_devices,
        old_devices,
    )

    _process_pcie_devices(add_func, data)
    _process_usb_devices(add_func, data)

    NodeDevice.objects.filter(
        id__in=[node_device.id for node_device in old_devices.values()]
    ).delete()


def _process_lxd_resources(node, data):
    """Process the resources results of the `LXD_OUTPUT_NAME` script."""
    resources = data["resources"]
    update_deployment_resources = node.status == NODE_STATUS.DEPLOYED
    # Update CPU details.
    node.cpu_count, node.cpu_speed, cpu_model, numa_nodes = parse_lxd_cpuinfo(
        resources
    )
    # Update memory.
    node.memory, hugepages_size, numa_nodes_info = _parse_memory(
        resources.get("memory", {}), numa_nodes
    )
    # Create or update NUMA nodes. This must be kept as a dictionary as not all
    # systems maintain linear continuity. e.g the PPC64 machine in our CI uses
    # 0, 1, 16, 17.
    numa_nodes = {}
    for numa_index, numa_data in numa_nodes_info.items():
        numa_node, _ = NUMANode.objects.update_or_create(
            node=node,
            index=numa_index,
            defaults={"memory": numa_data.memory, "cores": numa_data.cores},
        )
        if update_deployment_resources and hugepages_size:
            NUMANodeHugepages.objects.update_or_create(
                numanode=numa_node,
                page_size=hugepages_size,
                defaults={"total": numa_data.hugepages},
            )
        numa_nodes[numa_index] = numa_node

    network_devices = update_node_network_information(node, data, numa_nodes)
    storage_devices = update_node_physical_block_devices(
        node, resources, numa_nodes
    )

    update_node_devices(
        node, resources, numa_nodes, network_devices, storage_devices
    )

    if cpu_model:
        NodeMetadata.objects.update_or_create(
            node=node, key="cpu_model", defaults={"value": cpu_model}
        )

    _process_system_information(node, resources.get("system", {}))


def _parse_memory(memory, numa_nodes):
    total_memory = memory.get("total", 0)
    # currently LXD only supports default size for hugepages
    hugepages_size = memory.get("hugepages_size")
    default_numa_node = {"numa_node": 0, "total": total_memory}

    # fill NUMA nodes info
    for memory_node in memory.get("nodes", [default_numa_node]):
        numa_node = numa_nodes[memory_node["numa_node"]]
        numa_node.memory = int(memory_node.get("total", 0) / 1024 ** 2)
        numa_node.hugepages = memory_node.get("hugepages_total", 0)

    return int(total_memory / 1024 ** 2), hugepages_size, numa_nodes


def _get_tags_from_block_info(block_info):
    """Return array of tags that will populate the `PhysicalBlockDevice`.

    Tags block devices for:
        rotary: Storage device with a spinning disk.
        ssd: Storage device with flash storage.
        removable: Storage device that can be easily removed like a USB
            flash drive.
        sata: Storage device that is connected over SATA.
    """
    tags = []
    if block_info["rpm"]:
        tags.append("rotary")
        tags.append("%srpm" % block_info["rpm"])
    elif not block_info.get("maas_multipath"):
        tags.append("ssd")
    if block_info.get("maas_multipath"):
        tags.append("multipath")
    if block_info["removable"]:
        tags.append("removable")
    if block_info["type"] == "sata":
        tags.append("sata")
    return tags


def _get_matching_block_device(block_devices, serial=None, id_path=None):
    """Return the matching block device based on `serial` or `id_path` from
    the provided list of `block_devices`."""
    if serial:
        for block_device in block_devices:
            if block_device.serial == serial:
                return block_device
    elif id_path:
        for block_device in block_devices:
            if block_device.id_path == id_path:
                return block_device
    return None


def _condense_luns(disks):
    """Condense disks by LUN.

    LUNs are used in multipath devices to identify a single storage source
    for the operating system to use. Multiple disks may still show up on the
    system pointing to the same source using different paths. MAAS should only
    model one storage source and ignore the paths. On deployment Curtin will
    detect multipath and properly set it up.
    """
    serial_lun_map = defaultdict(list)
    processed_disks = []
    for disk in disks:
        # split the device path from the form "key1-value1-key2-value2..." into
        # a dict
        tokens = disk.get("device_path", "").split("-")
        device_path = dict(zip(tokens[::2], tokens[1::2]))
        # LXD does not currently give a pci_address, it's included in the
        # device_path. Add it if it isn't there. A USB disk include the
        # USB device and PCI device the USB controller is connected to.
        # Ignore USB devices as they are removable which MAAS doesn't
        # model.
        if (
            "pci" in device_path
            and "usb" not in device_path
            and "pci_address" not in disk
        ):
            disk["pci_address"] = device_path["pci"]
        if device_path.get("lun") not in ("0", None) and disk.get("serial"):
            # multipath devices have LUN different from 0
            serial_lun_map[(disk["serial"], device_path["lun"])].append(disk)
        else:
            processed_disks.append(disk)

    for (serial, lun), paths in serial_lun_map.items():
        # The first disk is usually the smallest id however doesn't usually
        # have the device_id associated with it.
        condensed_disk = paths[0]
        if len(paths) > 1:
            # Only tag a disk as multipath if it actually has multiple paths to
            # it.
            condensed_disk["maas_multipath"] = True
        for path in paths[1:]:
            # Make sure the disk processed has the lowest id. Each path is
            # given a name variant on a normal id. e.g sda, sdaa, sdab, sdb
            # sdba, sdbb results in just sda and sdb for two multipath disks.
            if path["id"] < condensed_disk["id"]:
                condensed_disk["id"] = path["id"]
                # The device differs per id, at least on IBM Z. MAAS doesn't
                # use the device but keep it consistent anyway.
                condensed_disk["device"] = path["device"]
            # Only one path is given the device_id. Make sure the disk that
            # is processed has it for the id_path.
            if not condensed_disk.get("device_id") and path.get("device_id"):
                condensed_disk["device_id"] = path["device_id"]
        processed_disks.append(condensed_disk)

    return sorted(processed_disks, key=itemgetter("id"))


def update_node_physical_block_devices(node, data, numa_nodes):
    block_devices = {}
    # Skip storage configuration if set by the user.
    if node.skip_storage:
        # Turn off skip_storage now that the hook has been called.
        node.skip_storage = False
        node.save(update_fields=["skip_storage"])
        return block_devices

    previous_block_devices = list(
        PhysicalBlockDevice.objects.filter(node=node).all()
    )
    for block_info in _condense_luns(data.get("storage", {}).get("disks", [])):
        # Skip the read-only devices or cdroms. We keep them in the output
        # for the user to view but they do not get an entry in the database.
        if block_info["read_only"] or block_info["type"] == "cdrom":
            continue
        name = block_info["id"]
        model = block_info.get("model", "")
        serial = block_info.get("serial", "")
        id_path = block_info.get("device_id", "")
        if id_path:
            id_path = f"/dev/disk/by-id/{id_path}"
        if not id_path or not serial:
            # Fallback to the dev path if device_path missing or there is
            # no serial number. (No serial number is a strong indicator that
            # this is a virtual disk, so it's unlikely that the device_path
            # would work.)
            id_path = "/dev/" + block_info.get("id")
        size = block_info.get("size")
        block_size = block_info.get("block_size")
        # If block_size is 0, set it to minimum default of 512.
        if not block_size:
            block_size = 512
        firmware_version = block_info.get("firmware_version")
        numa_index = block_info.get("numa_node")
        tags = _get_tags_from_block_info(block_info)

        # First check if there is an existing device with the same name.
        # If so, we need to rename it. Its name will be changed back later,
        # when we loop around to it.
        existing = PhysicalBlockDevice.objects.filter(
            node=node, name=name
        ).all()
        for device in existing:
            # Use the device ID to ensure a unique temporary name.
            device.name = "%s.%d" % (device.name, device.id)
            device.save(update_fields=["name"])

        block_device = _get_matching_block_device(
            previous_block_devices, serial, id_path
        )
        if block_device is not None:
            # Refresh, since it might have been temporarily renamed
            # above.
            block_device.refresh_from_db()
            # Already exists for the node. Keep the original object so the
            # ID doesn't change and if its set to the boot_disk that FK will
            # not need to be updated.
            previous_block_devices.remove(block_device)
            block_device.name = name
            block_device.model = model
            block_device.serial = serial
            block_device.id_path = id_path
            block_device.size = size
            block_device.block_size = block_size
            block_device.firmware_version = firmware_version
            block_device.tags = tags
            block_device.save()
        else:
            # MAAS doesn't allow disks smaller than 4MiB so skip them
            if size <= MIN_BLOCK_DEVICE_SIZE:
                continue
            # Skip loopback devices as they won't be available on next boot
            if id_path.startswith("/dev/loop"):
                continue

            # New block device. Create it on the node.
            block_device = PhysicalBlockDevice.objects.create(
                numa_node=numa_nodes[numa_index],
                name=name,
                id_path=id_path,
                size=size,
                block_size=block_size,
                tags=tags,
                model=model,
                serial=serial,
                firmware_version=firmware_version,
            )

        if block_info.get("pci_address"):
            block_devices[block_info["pci_address"]] = block_device
        elif block_info.get("usb_address"):
            block_devices[block_info["usb_address"]] = block_device

    # Clear boot_disk if it is being removed.
    boot_disk = node.boot_disk
    if boot_disk is not None and boot_disk in previous_block_devices:
        boot_disk = None
    if node.boot_disk != boot_disk:
        node.boot_disk = boot_disk
        node.save(update_fields=["boot_disk"])

    # XXX ltrager 11-16-2017 - Don't regenerate ScriptResults on controllers.
    # Currently this is not needed saving us 1 database query. However, if
    # commissioning is ever enabled for controllers regeneration will need
    # to be allowed on controllers otherwise storage testing may break.
    if node.current_testing_script_set is not None and not node.is_controller:
        # LP: #1731353 - Regenerate ScriptResults before deleting
        # PhyscalBlockDevices. This creates a ScriptResult with proper
        # parameters for each storage device on the system. Storage devices no
        # long available will be deleted which causes a casade delete on their
        # assoicated ScriptResults.
        node.current_testing_script_set.regenerate(storage=True, network=False)

    # Delete all the previous block devices that are no longer present
    # on the commissioned node.
    delete_block_device_ids = [bd.id for bd in previous_block_devices]
    if delete_block_device_ids:
        PhysicalBlockDevice.objects.filter(
            id__in=delete_block_device_ids
        ).delete()

    if not (node.status == NODE_STATUS.DEPLOYED and node.is_pod):
        # Layout needs to be set last so removed disks aren't included in the
        # applied layout. Deployed Pods should not have a layout set as the
        # layout of the deployed system is unknown.
        node.set_default_storage_layout()

    return block_devices


def _process_lxd_environment(node, data):
    """Process the environment results from the `LXD_OUTPUT_NAME` script."""
    # Verify the architecture is set correctly. This is how the architecture
    # gets set on controllers.
    node.architecture = kernel_to_debian_architecture(
        data["kernel_architecture"]
    )

    # When a machine is commissioning the OS will always be the ephemeral
    # environment. Controllers run the machine-resources binary directly
    # on the running machine and LXD Pods are getting this data from LXD
    # on the running machine. In those cases the information gathered below
    # is correct.
    if (
        (node.is_controller or node.is_pod)
        and data.get("os_name")
        and data.get("os_version")
    ):
        # This is how the hostname gets set on controllers and stays in sync on Pods.
        node.hostname = data["server_name"]

        # MAAS always stores OS information in lower case
        node.osystem = data["os_name"].lower()
        node.distro_series = data["os_version"].lower()
        # LXD always gives the OS version while MAAS stores Ubuntu releases
        # by release codename. e.g LXD gives 20.04 MAAS stores focal.
        if node.osystem == "ubuntu":
            release = get_release(node.distro_series)
            if release:
                node.distro_series = release["series"]


def process_lxd_results(node, output, exit_status):
    """Process the results of the `LXD_OUTPUT_NAME` script.

    If `exit_status` is non-zero, this function returns without doing
    anything.
    """
    if exit_status != 0:
        logger.error(
            "%s: lxd script failed with status: "
            "%s." % (node.hostname, exit_status)
        )
        return
    assert isinstance(output, bytes)
    try:
        data = json.loads(output.decode("utf-8"))
    except ValueError as e:
        raise ValueError(e.message + ": " + output)

    assert data.get("api_version") == "1.0", "Data not from LXD API 1.0!"

    # resources_network_usb and resources_disk_address are needed for mapping
    # between NodeDevices and Interfaces and BlockDevices. It is not included
    # on this list so MAAS can still use LXD < 4.9 as a VM host where this
    # information isn't necessary.
    required_extensions = {
        "resources",
        "resources_v2",
        "api_os",
        "resources_system",
        "resources_usb_pci",
    }
    missing_extensions = required_extensions - set(
        data.get("api_extensions", ())
    )
    assert (
        not missing_extensions
    ), f"Missing required LXD API extensions {sorted(missing_extensions)}"

    _process_lxd_environment(node, data["environment"])
    _process_lxd_resources(node, data)

    node.save()

    for pod in node.get_hosted_pods():
        pod.sync_hints_from_nodes()


def create_metadata_by_modalias(node, output: bytes, exit_status):
    """Tags the node based on discovered hardware, determined by modaliases.

    :param node: The node whose tags to set.
    :param output: Output from the LIST_MODALIASES_OUTPUT_NAME script
        (one modalias per line).
    :param exit_status: The exit status of the commissioning script.
    """
    if exit_status != 0:
        logger.error(
            "%s: modalias discovery script failed with status: %s"
            % (node.hostname, exit_status)
        )
        return
    assert isinstance(output, bytes)
    modaliases = output.decode("utf-8").splitlines()
    switch_tags_added, _ = retag_node_for_hardware_by_modalias(
        node, modaliases, SWITCH_TAG_NAME, SWITCH_HARDWARE
    )
    if switch_tags_added:
        dmi_data = get_dmi_data(modaliases)
        vendor, model = detect_switch_vendor_model(dmi_data)
        add_switch_vendor_model_tags(node, vendor, model)


def add_switch_vendor_model_tags(node, vendor, model):
    if vendor is not None:
        vendor_tag, _ = Tag.objects.get_or_create(name=vendor)
        node.tags.add(vendor_tag)
        logger.info(
            "%s: Added vendor tag '%s' for detected switch hardware."
            % (node.hostname, vendor)
        )
    if model is not None:
        kernel_opts = None
        if model == "wedge40":
            kernel_opts = "console=tty0 console=ttyS1,57600n8"
        elif model == "wedge100":
            kernel_opts = "console=tty0 console=ttyS4,57600n8"
        model_tag, _ = Tag.objects.get_or_create(
            name=model, defaults={"kernel_opts": kernel_opts}
        )
        node.tags.add(model_tag)
        logger.info(
            "%s: Added model tag '%s' for detected switch hardware."
            % (node.hostname, model)
        )


def update_node_fruid_metadata(node, output: bytes, exit_status):
    try:
        data = json.loads(output.decode("utf-8"))
    except json.decoder.JSONDecodeError:
        return

    # Attempt to map metadata provided by Facebook Wedge 100 FRUID API
    # to SNMP OID-like metadata describing physical nodes (see
    # http://www.ietf.org/rfc/rfc2737.txt).
    key_name_map = {
        "Product Name": NODE_METADATA.PHYSICAL_MODEL_NAME,
        "Product Serial Number": NODE_METADATA.PHYSICAL_SERIAL_NUM,
        "Product Version": NODE_METADATA.PHYSICAL_HARDWARE_REV,
        "System Manufacturer": NODE_METADATA.PHYSICAL_MFG_NAME,
    }
    info = data.get("Information", {})
    for fruid_key, node_key in key_name_map.items():
        if fruid_key in info:
            NodeMetadata.objects.update_or_create(
                node=node, key=node_key, defaults={"value": info[fruid_key]}
            )


def detect_switch_vendor_model(dmi_data):
    # This is based on:
    #    https://github.com/lool/sonic-snap/blob/master/common/id-switch
    vendor = None
    if "svnIntel" in dmi_data and "pnEPGSVR" in dmi_data:
        # XXX this seems like a suspicious assumption.
        vendor = "accton"
    elif "svnJoytech" in dmi_data and "pnWedge-AC-F20-001329" in dmi_data:
        vendor = "accton"
    elif "svnMellanoxTechnologiesLtd." in dmi_data:
        vendor = "mellanox"
    elif "svnTobefilledbyO.E.M." in dmi_data:
        if "rnPCOM-B632VG-ECC-FB-ACCTON-D" in dmi_data:
            vendor = "accton"
    # Now that we know the manufacturer, see if we can identify the model.
    model = None
    if vendor == "mellanox":
        if 'pn"MSN2100-CB2FO"' in dmi_data:
            model = "sn2100"
    elif vendor == "accton":
        if "pnEPGSVR" in dmi_data:
            model = "wedge40"
        elif "pnWedge-AC-F20-001329" in dmi_data:
            model = "wedge40"
        elif "pnTobefilledbyO.E.M." in dmi_data:
            if "rnPCOM-B632VG-ECC-FB-ACCTON-D" in dmi_data:
                model = "wedge100"
    return vendor, model


def get_dmi_data(modaliases):
    """Given the list of modaliases, returns the set of DMI data.

    An empty set will be returned if no DMI data could be found.

    The DMI data will be stripped of whitespace and have a prefix indicating
    what value they represent. Prefixes can be found in
    drivers/firmware/dmi-id.c in the Linux source:

        { "bvn", DMI_BIOS_VENDOR },
        { "bvr", DMI_BIOS_VERSION },
        { "bd",  DMI_BIOS_DATE },
        { "svn", DMI_SYS_VENDOR },
        { "pn",  DMI_PRODUCT_NAME },
        { "pvr", DMI_PRODUCT_VERSION },
        { "rvn", DMI_BOARD_VENDOR },
        { "rn",  DMI_BOARD_NAME },
        { "rvr", DMI_BOARD_VERSION },
        { "cvn", DMI_CHASSIS_VENDOR },
        { "ct",  DMI_CHASSIS_TYPE },
        { "cvr", DMI_CHASSIS_VERSION },

    The following is an example of what the set might look like:

        {'bd09/18/2014',
         'bvnAmericanMegatrendsInc.',
         'bvrMF1_2A04',
         'ct0',
         'cvnIntel',
         'cvrTobefilledbyO.E.M.',
         'pnEPGSVR',
         'pvrTobefilledbyO.E.M.',
         'rnTobefilledbyO.E.M.',
         'rvnTobefilledbyO.E.M.',
         'rvrTobefilledbyO.E.M.',
         'svnIntel'}

    :return: set
    """
    for modalias in modaliases:
        if modalias.startswith("dmi:"):
            return frozenset(
                [data for data in modalias.split(":")[1:] if data]
            )
    return frozenset()


def filter_modaliases(
    modaliases_discovered, modaliases=None, pci=None, usb=None
):
    """Determines which candidate modaliases match what was discovered.

    :param modaliases_discovered: The list of modaliases found on the node.
    :param modaliases: The candidate modaliases to match against. This
        parameter must be iterable. Wildcards are accepted.
    :param pci: A list of strings in the format <vendor>:<device>. May include
        wildcards.
    :param usb: A list of strings in the format <vendor>:<product>. May include
        wildcards.
    :return: The list of modaliases on the node matching the candidate(s).
    """
    patterns = []
    if modaliases is not None:
        patterns.extend(modaliases)
    if pci is not None:
        for pattern in pci:
            try:
                vendor, device = pattern.split(":")
            except ValueError:
                # Ignore malformed patterns.
                continue
            vendor = vendor.upper()
            device = device.upper()
            # v: vendor
            # d: device
            # sv: subvendor
            # sd: subdevice
            # bc: bus class
            # sc: bus subclass
            # i: interface
            patterns.append(
                "pci:v0000{vendor}d0000{device}sv*sd*bc*sc*i*".format(
                    vendor=vendor, device=device
                )
            )
    if usb is not None:
        for pattern in usb:
            try:
                vendor, product = pattern.split(":")
            except ValueError:
                # Ignore malformed patterns.
                continue
            vendor = vendor.upper()
            product = product.upper()
            # v: vendor
            # p: product
            # d: bcdDevice (device release number)
            # dc: device class
            # dsc: device subclass
            # dp: device protocol
            # ic: interface class
            # isc: interface subclass
            # ip: interface protocol
            patterns.append(
                "usb:v{vendor}p{product}d*dc*dsc*dp*ic*isc*ip*".format(
                    vendor=vendor, product=product
                )
            )
    matches = []
    for pattern in patterns:
        new_matches = fnmatch.filter(modaliases_discovered, pattern)
        for match in new_matches:
            if match not in matches:
                matches.append(match)
    return matches


def determine_hardware_matches(modaliases, hardware_descriptors):
    """Determines which hardware descriptors match the given modaliases.

    :param modaliases: List of modaliases found on the node.
    :param hardware_descriptors: Dictionary of information about each hardware
        component that can be discovered. This method requires a 'modaliases'
        entry to be present (with a list of modalias globs that might match
        the hardware on the node).
    :returns: A tuple whose first element contains the list of discovered
        hardware descriptors (with an added 'matches' element to specify which
        modaliases matched), and whose second element the list of any hardware
        that has been ruled out (so that the caller may remove those tags).
    """
    discovered_hardware = []
    ruled_out_hardware = []
    for candidate in hardware_descriptors:
        matches = filter_modaliases(modaliases, candidate["modaliases"])
        if matches:
            candidate = candidate.copy()
            candidate["matches"] = matches
            discovered_hardware.append(candidate)
        else:
            ruled_out_hardware.append(candidate)
    return discovered_hardware, ruled_out_hardware


def retag_node_for_hardware_by_modalias(
    node, modaliases, parent_tag_name, hardware_descriptors
):
    """Adds or removes tags on a node based on its modaliases.

    Returns the Tag model objects added and removed, respectively.

    :param node: The node whose tags to modify.
    :param modaliases: The modaliases discovered on the node.
    :param parent_tag_name: The tag name for the hardware type given in the
        `hardware_descriptors` list. For example, if switch ASICs are being
        discovered, the string "switch" might be appropriate. Then, if switch
        hardware is found, the node will be tagged with the matching
        descriptors' tag(s), *and* with the more general "switch" tag.
    :param hardware_descriptors: A list of hardware descriptor dictionaries.

    :returns: tuple of (tags_added, tags_removed)
    """
    # Don't unconditionally create the tag. Check for it with a filter first.
    parent_tag = get_one(Tag.objects.filter(name=parent_tag_name))
    tags_added = set()
    tags_removed = set()
    discovered_hardware, ruled_out_hardware = determine_hardware_matches(
        modaliases, hardware_descriptors
    )
    if discovered_hardware:
        if parent_tag is None:
            # Create the tag "just in time" if we found matching hardware, and
            # we hadn't created the tag yet.
            parent_tag = Tag(name=parent_tag_name)
            parent_tag.save()
        node.tags.add(parent_tag)
        tags_added.add(parent_tag)
        logger.info(
            "%s: Added tag '%s' for detected hardware type."
            % (node.hostname, parent_tag_name)
        )
        for descriptor in discovered_hardware:
            tag = descriptor["tag"]
            comment = descriptor["comment"]
            matches = descriptor["matches"]
            hw_tag, _ = Tag.objects.get_or_create(
                name=tag, defaults={"comment": comment}
            )
            node.tags.add(hw_tag)
            tags_added.add(hw_tag)
            logger.info(
                "%s: Added tag '%s' for detected hardware: %s "
                "(Matched: %s)." % (node.hostname, tag, comment, matches)
            )
    else:
        if parent_tag is not None:
            node.tags.remove(parent_tag)
            tags_removed.add(parent_tag)
            logger.info(
                "%s: Removed tag '%s'; machine does not match hardware "
                "description." % (node.hostname, parent_tag_name)
            )
    for descriptor in ruled_out_hardware:
        tag_name = descriptor["tag"]
        existing_tag = get_one(node.tags.filter(name=tag_name))
        if existing_tag is not None:
            node.tags.remove(existing_tag)
            tags_removed.add(existing_tag)
            logger.info(
                "%s: Removed tag '%s'; hardware is missing."
                % (node.hostname, tag_name)
            )
    return tags_added, tags_removed


# Register the post processing hooks.
NODE_INFO_SCRIPTS[GET_FRUID_DATA_OUTPUT_NAME][
    "hook"
] = update_node_fruid_metadata
NODE_INFO_SCRIPTS[LIST_MODALIASES_OUTPUT_NAME][
    "hook"
] = create_metadata_by_modalias
NODE_INFO_SCRIPTS[LXD_OUTPUT_NAME]["hook"] = process_lxd_results
NODE_INFO_SCRIPTS[KERNEL_CMDLINE_OUTPUT_NAME]["hook"] = update_boot_interface
