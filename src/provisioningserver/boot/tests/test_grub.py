# Copyright 2014-2021 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for `provisioningserver.boot.uefi_amd64`."""

import random
import re

from maastesting.factory import factory
from maastesting.testcase import MAASTestCase
from provisioningserver import boot
from provisioningserver.boot import BytesReader
from provisioningserver.boot.grub import re_config_file, UEFIAMD64BootMethod
from provisioningserver.boot.testing import TFTPPath, TFTPPathAndComponents
from provisioningserver.testing.config import ClusterConfigurationFixture
from provisioningserver.tests.test_kernel_opts import make_kernel_parameters
from provisioningserver.utils.network import convert_host_to_uri_str


def compose_config_path(
    mac: str = None, arch: str = None, subarch: str = None
) -> TFTPPath:
    """Compose the TFTP path for a UEFI configuration file.

    The path returned is relative to the TFTP root, as it would be
    identified by clients on the network.

    :param mac: A MAC address, in IEEE 802 colon-separated form,
        corresponding to the machine for which this configuration is
        relevant.
    :param arch: Architecture for the booting machine, for UEFI this is
        always amd64.
    :param subarch: Sub-architecture type, this is normally always generic.
    :return: Path for the corresponding PXE config file as exposed over
        TFTP, as a byte string.
    """
    if mac is not None:
        return f"grub/grub.cfg-{mac}".encode("ascii")
    if arch is not None:
        if subarch is None:
            subarch = "generic"
        return "grub/grub.cfg-{arch}-{subarch}".format(
            arch=arch, subarch=subarch
        ).encode("ascii")
    return b"grub/grub.cfg"


class TestUEFIAMD64BootMethodRender(MAASTestCase):
    """Tests for
    `provisioningserver.boot_amd64.uefi.UEFIAMD64BootMethod.render`."""

    def setUp(self):
        super().setUp()
        boot.debug_enabled.cache_clear()
        self.addClassCleanup(boot.debug_enabled.cache_clear)
        self.useFixture(ClusterConfigurationFixture(debug=False))

    def test_get_reader_tftp(self):
        # Given the right configuration options, the UEFI configuration is
        # correctly rendered.
        method = UEFIAMD64BootMethod()
        params = make_kernel_parameters(arch="amd64", purpose="xinstall")
        fs_host = re.escape(
            f"(http,{convert_host_to_uri_str(params.fs_host)}:5248)/images"
        )
        output = method.get_reader(
            backend=None, kernel_params=params, protocol="tftp"
        )
        # The output is a BytesReader.
        self.assertIsInstance(output, BytesReader)
        output = output.read(10000).decode("utf-8")
        # The template has rendered without error. UEFI configurations
        # typically start with a DEFAULT line.
        self.assertTrue(output.startswith('set default="0"'))
        # The UEFI parameters are all set according to the options.

        for regex in [
            r"(?ms).*\s+lin.*cc:\\{\'datasource_list\': \[\'MAAS\'\]\\}end_cc.*",
            rf"(?ms).*^\s+linux  {fs_host}/{params.kernel} .+?$",
            rf"(?ms).*^\s+initrd {fs_host}/{params.initrd}$",
        ]:
            self.assertRegex(output, regex)

    def test_get_reader_http(self):
        # Given the right configuration options, the UEFI configuration is
        # correctly rendered.
        method = UEFIAMD64BootMethod()
        params = make_kernel_parameters(arch="amd64", purpose="xinstall")
        output = method.get_reader(
            backend=None, kernel_params=params, protocol="http"
        )
        # The output is a BytesReader.
        self.assertIsInstance(output, BytesReader)
        output = output.read(10000).decode("utf-8")
        # The template has rendered without error. UEFI configurations
        # typically start with a DEFAULT line.
        self.assertTrue(output.startswith('set default="0"'))
        # The UEFI parameters are all set according to the options.
        for regex in [
            r"(?ms).*\s+lin.*cc:\\{\'datasource_list\': \[\'MAAS\'\]\\}end_cc.*",
            rf"(?ms).*^\s+linux  /images/{params.kernel} .+?$",
            rf"(?ms).*^\s+initrd /images/{params.initrd}$",
        ]:
            self.assertRegex(output, regex)

    def test_get_reader_with_extra_arguments_does_not_affect_output(self):
        # get_reader() allows any keyword arguments as a safety valve.
        method = UEFIAMD64BootMethod()
        options = {
            "backend": None,
            "kernel_params": make_kernel_parameters(purpose="xinstall"),
            "protocol": random.choice(["tftp", "http"]),
        }
        # Capture the output before sprinking in some random options.
        output_before = method.get_reader(**options).read(10000)
        # Sprinkle some magic in.
        options.update(
            (factory.make_name("name"), factory.make_name("value"))
            for _ in range(10)
        )
        # Capture the output after sprinking in some random options.
        output_after = method.get_reader(**options).read(10000)
        # The generated template is the same.
        self.assertEqual(output_before, output_after)

    def test_get_reader_with_local_purpose(self):
        # If purpose is "local", the config.localboot.template should be
        # used.
        method = UEFIAMD64BootMethod()
        options = {
            "backend": None,
            "kernel_params": make_kernel_parameters(
                purpose="local", arch="amd64"
            ),
            "protocol": random.choice(["tftp", "http"]),
        }
        output = method.get_reader(**options).read(10000).decode("utf-8")
        self.assertIn("chainloader /efi/", output)
        self.assertIn("bootx64.efi", output)
        self.assertIn("shimx64.efi", output)
        self.assertIn("grubx64.efi", output)

    def test_get_reader_with_enlist_purpose(self):
        # If purpose is "enlist", the config.enlist.template should be
        # used.
        method = UEFIAMD64BootMethod()
        params = make_kernel_parameters(purpose="enlist", arch="amd64")
        options = {
            "backend": None,
            "kernel_params": params,
            "protocol": random.choice(["tftp", "http"]),
        }
        output = method.get_reader(**options).read(10000).decode("utf-8")
        for needle in [
            "menuentry 'Ephemeral'",
            f"{params.osystem}/{params.arch}/{params.subarch}",
            params.kernel,
        ]:
            self.assertIn(needle, output)

    def test_get_reader_with_commissioning_purpose(self):
        # If purpose is "commissioning", the config.commissioning.template
        # should be used.
        method = UEFIAMD64BootMethod()
        params = make_kernel_parameters(purpose="commissioning", arch="amd64")
        options = {
            "backend": None,
            "kernel_params": params,
            "protocol": random.choice(["tftp", "http"]),
        }
        output = method.get_reader(**options).read(10000).decode("utf-8")
        for needle in [
            "menuentry 'Ephemeral'",
            f"{params.osystem}/{params.arch}/{params.subarch}",
            params.kernel,
        ]:
            self.assertIn(needle, output)


class TestUEFIAMD64BootMethodRegex(MAASTestCase):
    """Tests
    `provisioningserver.boot.uefi_amd64.UEFIAMD64BootMethod.re_config_file`."""

    @staticmethod
    def get_example_path_and_components() -> TFTPPathAndComponents:
        """Return a plausible UEFI path and its components.

        The path is intended to match `re_config_file`, and
        the components are the expected groups from a match.
        """
        mac = factory.make_mac_address(":")
        return (
            compose_config_path(mac),
            {"mac": mac.encode("ascii"), "arch": None, "subarch": None},
        )

    def test_re_config_file_is_compatible_with_cfg_path_generator(self):
        # The regular expression for extracting components of the file path is
        # compatible with the PXE config path generator.
        for iteration in range(10):  # noqa: B007
            config_path, args = self.get_example_path_and_components()
            match = re_config_file.match(config_path)
            self.assertIsNotNone(match, config_path)
            self.assertEqual(args, match.groupdict())

    def test_re_config_file_with_leading_slash(self):
        # The regular expression for extracting components of the file path
        # doesn't care if there's a leading forward slash; the TFTP server is
        # easy on this point, so it makes sense to be also.
        config_path, args = self.get_example_path_and_components()
        # Ensure there's a leading slash.
        config_path = b"/" + config_path.lstrip(b"/")
        match = re_config_file.match(config_path)
        self.assertIsNotNone(match, config_path)
        self.assertEqual(args, match.groupdict())

    def test_re_config_file_without_leading_slash(self):
        # The regular expression for extracting components of the file path
        # doesn't care if there's no leading forward slash; the TFTP server is
        # easy on this point, so it makes sense to be also.
        config_path, args = self.get_example_path_and_components()
        # Ensure there's no leading slash.
        config_path = config_path.lstrip(b"/")
        match = re_config_file.match(config_path)
        self.assertIsNotNone(match, config_path)
        self.assertEqual(args, match.groupdict())

    def test_re_config_file_matches_classic_grub_cfg(self):
        # The default config path is simply "grub.cfg-{mac}" (without
        # leading slash).  The regex matches this.
        mac = b"aa:bb:cc:dd:ee:ff"
        match = re_config_file.match(b"grub/grub.cfg-%s" % mac)
        self.assertIsNotNone(match)
        self.assertEqual(
            {"mac": mac, "arch": None, "subarch": None}, match.groupdict()
        )

    def test_re_config_file_matches_grub_cfg_with_leading_slash(self):
        mac = b"aa:bb:cc:dd:ee:ff"
        match = re_config_file.match(b"/grub/grub.cfg-%s" % mac)
        self.assertIsNotNone(match)
        self.assertEqual(
            {"mac": mac, "arch": None, "subarch": None}, match.groupdict()
        )

    def test_re_config_file_does_not_match_default_grub_config_file(self):
        # The default grub.cfg is on the filesystem let the normal handler
        # grab it.
        self.assertIsNone(re_config_file.match(b"grub/grub.cfg"))

    def test_re_config_file_with_default(self):
        match = re_config_file.match(b"grub/grub.cfg-default")
        self.assertIsNotNone(match)
        self.assertEqual(
            {"mac": None, "arch": None, "subarch": None}, match.groupdict()
        )

    def test_re_config_file_with_default_arch(self):
        arch = factory.make_name("arch", sep="").encode("ascii")
        match = re_config_file.match(b"grub/grub.cfg-default-%s" % arch)
        self.assertIsNotNone(match)
        self.assertEqual(
            {"mac": None, "arch": arch, "subarch": None}, match.groupdict()
        )

    def test_re_config_file_with_default_arch_and_subarch(self):
        arch = factory.make_name("arch", sep="").encode("ascii")
        subarch = factory.make_name("subarch", sep="").encode("ascii")
        match = re_config_file.match(
            b"grub/grub.cfg-default-%s-%s" % (arch, subarch)
        )
        self.assertIsNotNone(match)
        self.assertEqual(
            {"mac": None, "arch": arch, "subarch": subarch}, match.groupdict()
        )


class TestUEFIAMD64BootMethod(MAASTestCase):
    """Tests `provisioningserver.boot.uefi_amd64.UEFIAMD64BootMethod`."""

    def test_match_path_none(self):
        method = UEFIAMD64BootMethod()
        backend = random.choice(["http", "tftp"])
        self.assertIsNone(
            method.match_path(backend, factory.make_string().encode())
        )

    def test_match_path_mac_colon(self):
        method = UEFIAMD64BootMethod()
        backend = random.choice(["http", "tftp"])
        mac = factory.make_mac_address()
        self.assertEqual(
            {"mac": mac.replace(":", "-")},
            method.match_path(backend, f"/grub/grub.cfg-{mac}".encode()),
        )

    def test_match_path_mac_dash(self):
        method = UEFIAMD64BootMethod()
        backend = random.choice(["http", "tftp"])
        mac = factory.make_mac_address().replace(":", "-")
        self.assertEqual(
            {"mac": mac},
            method.match_path(backend, f"/grub/grub.cfg-{mac}".encode()),
        )

    def test_match_path_arch(self):
        method = UEFIAMD64BootMethod()
        backend = random.choice(["http", "tftp"])
        arch = factory.make_string()
        self.assertEqual(
            {"arch": arch},
            method.match_path(
                backend, f"/grub/grub.cfg-default-{arch}".encode()
            ),
        )

    def test_match_path_arch_x86_64(self):
        method = UEFIAMD64BootMethod()
        backend = random.choice(["http", "tftp"])
        self.assertEqual(
            {"arch": "amd64"},
            method.match_path(backend, b"/grub/grub.cfg-default-x86_64"),
        )

    def test_match_path_arch_powerpc(self):
        method = UEFIAMD64BootMethod()
        backend = random.choice(["http", "tftp"])
        self.assertEqual(
            {"arch": "ppc64el"},
            method.match_path(backend, b"/grub/grub.cfg-default-powerpc"),
        )

    def test_match_path_arch_ppc64(self):
        method = UEFIAMD64BootMethod()
        backend = random.choice(["http", "tftp"])
        self.assertEqual(
            {"arch": "ppc64el"},
            method.match_path(backend, b"/grub/grub.cfg-default-ppc64"),
        )

    def test_match_path_arch_ppc64le(self):
        method = UEFIAMD64BootMethod()
        backend = random.choice(["http", "tftp"])
        self.assertEqual(
            {"arch": "ppc64el"},
            method.match_path(backend, b"/grub/grub.cfg-default-ppc64le"),
        )

    def test_match_path_arch_subarch(self):
        method = UEFIAMD64BootMethod()
        backend = random.choice(["http", "tftp"])
        arch = factory.make_string()
        subarch = factory.make_string()
        self.assertEqual(
            {"arch": arch, "subarch": subarch},
            method.match_path(
                backend, f"/grub/grub.cfg-default-{arch}-{subarch}".encode()
            ),
        )
