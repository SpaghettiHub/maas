from maascommon.enums.node import HARDWARE_TYPE, NODE_DEVICE_BUS
from maasserver.testing.factory import factory


def make_pci_devices(machines: list):
    for machine in machines:
        for hw_type in [
            HARDWARE_TYPE.NODE,
            HARDWARE_TYPE.CPU,
            HARDWARE_TYPE.MEMORY,
            HARDWARE_TYPE.GPU,
        ]:
            factory.make_NodeDevice(
                bus=NODE_DEVICE_BUS.PCIE,
                node=machine,
                hardware_type=hw_type,
            )
        factory.make_NodeDevice(
            bus=NODE_DEVICE_BUS.PCIE,
            node=machine,
            hardware_type=HARDWARE_TYPE.GPU,
            vendor_id="cafe",
            product_id="cafe",
        )
