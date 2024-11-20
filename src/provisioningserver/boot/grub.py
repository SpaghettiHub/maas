# Copyright 2014-2021 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""UEFI AMD64 Boot Method"""


from itertools import repeat
import os
import re
from textwrap import dedent

from maascommon.bootmethods import (
    OpenFirmwarePpc64elBootMetadata,
    UefiAmd64BootMetadata,
    UefiAmd64HttpBootMetadata,
    UefiArm64BootMetadata,
    UefiArm64HttpBootMetadata,
    UefiEbcBootMetadata,
)
from provisioningserver.boot import BootMethod, BytesReader, get_parameters
from provisioningserver.kernel_opts import compose_kernel_command_line
from provisioningserver.logger import get_maas_logger
from provisioningserver.utils.network import convert_host_to_uri_str

maaslog = get_maas_logger("uefi_amd64")


# Ideally this would be embedded in the default GRUB image(LP:1923268)
# Protocol MUST be left out so GRUB continues to use whatever protocol
# was used during boot. e.g if the config file is prepended with (pxe)
# GRUB will always use TFTP.
CONFIG_FILE = dedent(
    """
    # MAAS GRUB2 pre-loader configuration file

    # Load based on MAC address first.
    configfile /grub/grub.cfg-${net_default_mac}

    # Failed to load based on MAC address. Load based on the CPU
    # architecture.
    configfile /grub/grub.cfg-default-${grub_cpu}
    """
)

# GRUB EFINET represents a MAC address in IEEE 802 colon-seperated
# format. Required for UEFI as GRUB2 only presents the MAC address
# in colon-seperated format.
re_mac_address_octet = r"[0-9a-f]{2}"
re_mac_address = re.compile("[:-]".join(repeat(re_mac_address_octet, 6)))

# Match the grub/grub.cfg-* request for UEFI (aka. GRUB2)
re_config_file = r"""
    # Optional leading slash(es).
    ^/*
    grub/grub[.]cfg   # UEFI (aka. GRUB2) expects this.
    -
    (?: # either a MAC
        (?P<mac>{re_mac_address.pattern}) # Capture UEFI MAC.
    | # or "default"
        default
            (?: # perhaps with specified arch, with a separator of '-'
            [-](?P<arch>\w+) # arch
            (?:-(?P<subarch>\w+))? # optional subarch
            )?
    )
    $
"""

re_config_file = re_config_file.format(re_mac_address=re_mac_address)
re_config_file = re_config_file.encode("ascii")
re_config_file = re.compile(re_config_file, re.VERBOSE)


class UEFIAMD64BootMethod(BootMethod, UefiAmd64BootMetadata):

    def match_path(self, backend, path):
        """Checks path for the configuration file that needs to be
        generated.

        :param backend: requesting backend
        :param path: requested path
        :return: dict of match params from path, None if no match
        """
        match = re_config_file.match(path)
        if match is None:
            return None
        params = get_parameters(match)

        # MAC address is in the wrong format, fix it
        mac = params.get("mac")
        if mac is not None:
            params["mac"] = mac.replace(":", "-")

        # MAAS uses Debian architectures while GRUB uses standard Linux
        # architectures.
        arch = params.get("arch")
        if arch == "x86_64":
            params["arch"] = "amd64"
        elif arch in {"powerpc", "ppc64", "ppc64le"}:
            params["arch"] = "ppc64el"

        return params

    def get_reader(self, backend, kernel_params, protocol, **extra):
        """Render a configuration file as a unicode string.

        :param backend: requesting backend
        :param kernel_params: An instance of `KernelParameters`.
        :param protocol: The protocol the transfer is happening over.
        :param extra: Allow for other arguments. This is a safety valve;
            parameters generated in another component (for example, see
            `TFTPBackend.get_boot_method_reader`) won't cause this to break.
        """

        def kernel_command(params):
            """Return the kernel command, adjusted for UEFI to work.

            See the similar function in BootMethod, and the callsite below.

            The issue here is that grub throws a fit when the braces on
            cc:{...}end_cc are hit, for whatever reason.  Escape _JUST_ those.
            """
            return re.sub(
                r"cc:{(?P<inner>[^}]*)}end_cc",
                r"cc:\{\g<inner>\}end_cc",
                compose_kernel_command_line(params),
            )

        template = self.get_template(
            kernel_params.purpose, kernel_params.arch, kernel_params.subarch
        )
        namespace = self.compose_template_namespace(kernel_params)

        # TFTP is much slower than HTTP. If GRUB was transfered over TFTP use
        # GRUBs internal HTTP implementation to download the kernel and initrd.
        # If HTTP or HTTPS was used don't specify host to continue to use the
        # UEFI firmware's internal HTTP implementation.
        if protocol == "tftp":
            namespace["fs_efihost"] = "(http,%s:5248)/images/" % (
                convert_host_to_uri_str(kernel_params.fs_host)
            )
        else:
            namespace["fs_efihost"] = "/images/"

        # Bug#1651452 - kernel command needs some extra escapes, but ONLY for
        # UEFI.  And so we fix it here, instead of in the common code.  See
        # also src/provisioningserver/kernel_opts.py.
        namespace["kernel_command"] = kernel_command
        return BytesReader(
            template.substitute(namespace).strip().encode("utf-8")
        )

    def install_templates(self, destination: str):
        config_path = os.path.join(destination, "grub")
        config_dst = os.path.join(config_path, "grub.cfg")
        if not os.path.exists(config_path):
            os.makedirs(config_path)
        if not os.path.exists(config_dst):
            with open(config_dst, "wb") as stream:
                stream.write(CONFIG_FILE.encode("utf-8"))


class UEFIAMD64HTTPBootMethod(UEFIAMD64BootMethod, UefiAmd64HttpBootMetadata):
    pass


class UEFIEBCBootMethod(UEFIAMD64BootMethod, UefiEbcBootMetadata):
    pass


class UEFIARM64BootMethod(UEFIAMD64BootMethod, UefiArm64BootMetadata):
    pass


class UEFIARM64HTTPBootMethod(UEFIARM64BootMethod, UefiArm64HttpBootMetadata):
    pass


class OpenFirmwarePPC64ELBootMethod(
    UEFIAMD64BootMethod, OpenFirmwarePpc64elBootMetadata
):
    pass
