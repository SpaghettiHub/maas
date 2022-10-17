# Copyright 2016-2021 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

import random
from textwrap import dedent

from netaddr import IPAddress
import tempita
from testtools.matchers import (
    Contains,
    ContainsDict,
    Equals,
    Is,
    IsInstance,
    KeysEqual,
    MatchesDict,
    Not,
)
import yaml

from maasserver.enum import NODE_STATUS
from maasserver.models import Config, ControllerInfo, NodeMetadata
from maasserver.node_status import COMMISSIONING_LIKE_STATUSES
from maasserver.server_address import get_maas_facing_server_host
from maasserver.testing.factory import factory
from maasserver.testing.fixtures import RBACEnabled
from maasserver.testing.testcase import MAASServerTestCase
from maasserver.utils.converters import systemd_interval_to_calendar
from maasserver.utils.orm import reload_object
from maastesting.matchers import MockNotCalled
from metadataserver import vendor_data
from metadataserver.vendor_data import (
    _get_metadataserver_template,
    _get_node_admin_token,
    generate_ephemeral_deployment_network_configuration,
    generate_ephemeral_netplan_lock_removal,
    generate_hardware_sync_systemd_configuration,
    generate_kvm_pod_configuration,
    generate_ntp_configuration,
    generate_rack_controller_configuration,
    generate_snap_configuration,
    generate_system_info,
    get_node_maas_url,
    get_node_rack_url,
    get_vendor_data,
    HARDWARE_SYNC_MACHINE_TOKEN_PATH,
    HARDWARE_SYNC_SERVICE_TEMPLATE,
    HARDWARE_SYNC_TIMER_TEMPLATE,
    LXD_CERTIFICATE_METADATA_KEY,
    VIRSH_PASSWORD_METADATA_KEY,
)
from provisioningserver.drivers.pod.lxd import LXD_MAAS_PROJECT_CONFIG


class TestGetVendorData(MAASServerTestCase):
    """Tests for `get_vendor_data`."""

    def test_returns_dict(self):
        node = factory.make_Node()
        self.assertThat(get_vendor_data(node, None), IsInstance(dict))

    def test_combines_key_values(self):
        controller = factory.make_RackController()
        ControllerInfo.objects.set_version(controller, "3.0.0-123-g.abc")
        secret = factory.make_string()
        Config.objects.set_config("rpc_shared_secret", secret)
        node = factory.make_Node(
            netboot=False, install_rackd=True, osystem="ubuntu"
        )
        config = get_vendor_data(node, None)
        self.assertEqual(
            config["runcmd"],
            [
                "snap install maas --channel=3.0/stable",
                f"/snap/bin/maas init rack --maas-url http://localhost:5240/MAAS --secret {secret}",
                "rm -rf /run/netplan",
            ],
        )

    def test_includes_no_system_information_if_no_default_user(self):
        node = factory.make_Node(owner=factory.make_User())
        vendor_data = get_vendor_data(node, None)
        self.assertThat(vendor_data, Not(Contains("system_info")))

    def test_includes_system_information_if_default_user(self):
        owner = factory.make_User()
        node = factory.make_Node(owner=owner, default_user=owner)
        vendor_data = get_vendor_data(node, None)
        self.assertThat(
            vendor_data,
            ContainsDict(
                {
                    "system_info": MatchesDict(
                        {"default_user": KeysEqual("name", "gecos")}
                    )
                }
            ),
        )

    def test_includes_ntp_server_information(self):
        Config.objects.set_config("ntp_external_only", True)
        Config.objects.set_config("ntp_servers", "foo bar")
        node = factory.make_Node()
        vendor_data = get_vendor_data(node, None)
        self.assertThat(
            vendor_data,
            ContainsDict(
                {"ntp": Equals({"servers": [], "pools": ["bar", "foo"]})}
            ),
        )


class TestGenerateSystemInfo(MAASServerTestCase):
    """Tests for `generate_system_info`."""

    def test_yields_nothing_when_node_has_no_owner(self):
        node = factory.make_Node()
        self.assertThat(node.owner, Is(None))
        configuration = generate_system_info(node)
        self.assertThat(dict(configuration), Equals({}))

    def test_yields_nothing_when_owner_and_no_default_user(self):
        node = factory.make_Node()
        self.assertThat(node.owner, Is(None))
        self.assertThat(node.default_user, Is(""))
        configuration = generate_system_info(node)
        self.assertThat(dict(configuration), Equals({}))

    def test_yields_basic_system_info_when_node_owned_with_default_user(self):
        owner = factory.make_User()
        owner.first_name = "First"
        owner.last_name = "Last"
        owner.save()
        node = factory.make_Node(owner=owner, default_user=owner)
        configuration = generate_system_info(node)
        self.assertThat(
            dict(configuration),
            Equals(
                {
                    "system_info": {
                        "default_user": {
                            "name": owner.username,
                            "gecos": "First Last,,,,",
                        }
                    }
                }
            ),
        )


class TestGenerateSnapConfiguration(MAASServerTestCase):
    def test_no_proxy(self):
        node = factory.make_Node()
        config = generate_snap_configuration(node, None)
        self.assertEqual(list(config), [])

    def test_proxy(self):
        node = factory.make_Node()
        config = generate_snap_configuration(node, "http://proxy.example.com/")
        self.assertEqual(
            list(config),
            [
                (
                    "snap",
                    {
                        "commands": [
                            'snap set system proxy.http="http://proxy.example.com/" proxy.https="http://proxy.example.com/"'
                        ],
                    },
                ),
            ],
        )


class TestGenerateNTPConfiguration(MAASServerTestCase):
    """Tests for `generate_ntp_configuration`."""

    def test_external_only_yields_nothing_when_no_ntp_servers_defined(self):
        Config.objects.set_config("ntp_external_only", True)
        Config.objects.set_config("ntp_servers", "")
        configuration = generate_ntp_configuration(node=factory.make_Node())
        self.assertThat(dict(configuration), Equals({}))

    def test_external_only_yields_all_ntp_servers_when_defined(self):
        Config.objects.set_config("ntp_external_only", True)
        ntp_hosts = factory.make_hostname(), factory.make_hostname()
        ntp_addrs = factory.make_ipv4_address(), factory.make_ipv6_address()
        ntp_servers = ntp_hosts + ntp_addrs
        Config.objects.set_config("ntp_servers", " ".join(ntp_servers))
        configuration = generate_ntp_configuration(node=factory.make_Node())
        self.assertThat(
            dict(configuration),
            Equals(
                {
                    "ntp": {
                        "servers": sorted(ntp_addrs, key=IPAddress),
                        "pools": sorted(ntp_hosts),
                    }
                }
            ),
        )

    def test_yields_nothing_when_machine_has_no_boot_cluster_address(self):
        Config.objects.set_config("ntp_external_only", False)
        machine = factory.make_Machine()
        machine.boot_cluster_ip = None
        machine.save()
        configuration = generate_ntp_configuration(machine)
        self.assertThat(dict(configuration), Equals({}))

    def test_yields_boot_cluster_address_when_machine_has_booted(self):
        Config.objects.set_config("ntp_external_only", False)

        machine = factory.make_Machine()
        address = factory.make_StaticIPAddress(
            interface=factory.make_Interface(node=machine)
        )

        rack_primary = factory.make_RackController(subnet=address.subnet)
        rack_primary_address = factory.make_StaticIPAddress(
            interface=factory.make_Interface(node=rack_primary),
            subnet=address.subnet,
        )

        rack_secondary = factory.make_RackController(subnet=address.subnet)
        rack_secondary_address = factory.make_StaticIPAddress(
            interface=factory.make_Interface(node=rack_secondary),
            subnet=address.subnet,
        )

        vlan = address.subnet.vlan
        vlan.primary_rack = rack_primary
        vlan.secondary_rack = rack_secondary
        vlan.dhcp_on = True
        vlan.save()

        configuration = generate_ntp_configuration(machine)
        self.assertThat(
            dict(configuration),
            Equals(
                {
                    "ntp": {
                        "servers": sorted(
                            (
                                rack_primary_address.ip,
                                rack_secondary_address.ip,
                            ),
                            key=IPAddress,
                        ),
                        "pools": [],
                    }
                }
            ),
        )


class TestGenerateRackControllerConfiguration(MAASServerTestCase):
    def test_yields_nothing_when_node_is_not_netboot_disabled(self):
        node = factory.make_Node(osystem="ubuntu", install_rackd=True)
        configuration = generate_rack_controller_configuration(
            node=node,
        )
        self.assertEqual(list(configuration), [])

    def test_yields_nothing_when_node_is_not_ubuntu(self):
        node = factory.make_Node(
            osystem="centos", netboot=False, install_rackd=True
        )
        configuration = generate_rack_controller_configuration(node)
        self.assertEqual(list(configuration), [])

    def test_yields_configuration_with_ubuntu(self):
        controller = factory.make_RackController()
        ControllerInfo.objects.set_version(controller, "3.0.0-123-g.abc")
        node = factory.make_Node(
            osystem="ubuntu", netboot=False, install_rackd=True
        )
        configuration = generate_rack_controller_configuration(node)
        secret = "1234"
        Config.objects.set_config("rpc_shared_secret", secret)
        maas_url = "http://%s:5240/MAAS" % get_maas_facing_server_host(
            node.get_boot_rack_controller()
        )
        self.assertEqual(
            list(configuration),
            [
                (
                    "runcmd",
                    [
                        "snap install maas --channel=3.0/stable",
                        f"/snap/bin/maas init rack --maas-url {maas_url} --secret {secret}",
                    ],
                ),
            ],
        )

    def test_yields_nothing_when_machine_install_rackd_false(self):
        node = factory.make_Node(
            osystem="ubuntu", netboot=False, install_rackd=False
        )
        configuration = generate_rack_controller_configuration(node)
        self.assertEqual(list(configuration), [])

    def test_yields_configuration_when_machine_install_rackd_true(self):
        controller = factory.make_RackController()
        ControllerInfo.objects.set_version(controller, "3.0.0-123-g.abc")
        node = factory.make_Node(
            osystem="ubuntu", netboot=False, install_rackd=True
        )
        configuration = generate_rack_controller_configuration(node)
        secret = "1234"
        Config.objects.set_config("rpc_shared_secret", secret)
        maas_url = "http://%s:5240/MAAS" % get_maas_facing_server_host(
            node.get_boot_rack_controller()
        )
        self.assertEqual(
            list(configuration),
            [
                (
                    "runcmd",
                    [
                        "snap install maas --channel=3.0/stable",
                        f"/snap/bin/maas init rack --maas-url {maas_url} --secret {secret}",
                    ],
                ),
            ],
        )


class TestGenerateKVMPodConfiguration(MAASServerTestCase):
    def test_yields_configuration_when_machine_install_kvm_true(self):
        password = "123secure"
        self.patch(vendor_data, "_generate_password").return_value = password
        self.patch(vendor_data, "crypt").return_value = "123crypted"
        node = factory.make_Node(
            status=NODE_STATUS.DEPLOYING,
            osystem="ubuntu",
            netboot=False,
            install_kvm=True,
        )
        factory.make_NodeMetadata(
            key=VIRSH_PASSWORD_METADATA_KEY,
            node=node,
            value="old value",
        )
        cred_lxd = factory.make_NodeMetadata(
            key=LXD_CERTIFICATE_METADATA_KEY,
            node=node,
            value="old value",
        )

        config = list(generate_kvm_pod_configuration(node))
        self.assertEqual(
            config,
            [
                ("ssh_pwauth", True),
                (
                    "users",
                    [
                        "default",
                        {
                            "name": "virsh",
                            "lock_passwd": False,
                            "passwd": "123crypted",
                            "shell": "/bin/rbash",
                        },
                    ],
                ),
                ("packages", ["libvirt-daemon-system", "libvirt-clients"]),
                (
                    "runcmd",
                    [
                        "mkdir -p /home/virsh/bin",
                        "ln -s /usr/bin/virsh /home/virsh/bin/virsh",
                        "/usr/sbin/usermod --append --groups libvirt,libvirt-qemu virsh",
                        "systemctl restart sshd",
                    ],
                ),
                (
                    "write_files",
                    [
                        {
                            "content": "PATH=/home/virsh/bin",
                            "path": "/home/virsh/.bash_profile",
                        },
                        {
                            "content": dedent(
                                """\
                                Match user virsh
                                  X11Forwarding no
                                  AllowTcpForwarding no
                                  PermitTTY no
                                  ForceCommand nc -q 0 -U /var/run/libvirt/libvirt-sock
                                """
                            ),
                            "path": "/etc/ssh/sshd_config",
                            "append": True,
                        },
                    ],
                ),
            ],
        )
        password_meta = NodeMetadata.objects.first()
        self.assertEqual(password_meta.key, "virsh_password")
        self.assertEqual(password_meta.value, password)
        self.assertIsNone(reload_object(cred_lxd))

    def test_yields_configuration_when_machine_register_vmhost_true(self):
        cert = vendor_data.generate_certificate("maas")
        self.patch(vendor_data, "generate_certificate").return_value = cert
        node = factory.make_Node(
            status=NODE_STATUS.DEPLOYING,
            osystem="ubuntu",
            netboot=False,
            register_vmhost=True,
        )
        cred_virsh = factory.make_NodeMetadata(
            key=VIRSH_PASSWORD_METADATA_KEY,
            node=node,
            value="old value",
        )
        factory.make_NodeMetadata(
            key=LXD_CERTIFICATE_METADATA_KEY,
            node=node,
            value="old value",
        )
        config = list(generate_kvm_pod_configuration(node))
        self.assertEqual(
            config,
            [
                (
                    "write_files",
                    [
                        {
                            "content": cert.certificate_pem(),
                            "path": "/root/lxd.crt",
                        },
                        {
                            "content": yaml.safe_dump(LXD_MAAS_PROJECT_CONFIG),
                            "path": "/root/maas-project.yaml",
                        },
                    ],
                ),
                (
                    "runcmd",
                    [
                        "apt autoremove --purge --yes lxd lxd-client lxcfs",
                        "snap install lxd --channel=latest",
                        "snap refresh lxd --channel=latest",
                        "lxd init --auto --network-address=[::]",
                        "lxc project create maas",
                        "sh -c 'lxc project edit maas </root/maas-project.yaml'",
                        "lxc config trust add /root/lxd.crt --restricted --projects maas",
                        "rm /root/lxd.crt /root/maas-project.yaml",
                    ],
                ),
            ],
        )
        creds_meta = NodeMetadata.objects.first()
        self.assertEqual(creds_meta.key, "lxd_certificate")
        self.assertEqual(
            creds_meta.value, cert.certificate_pem() + cert.private_key_pem()
        )
        self.assertIsNone(reload_object(cred_virsh))

    def test_includes_smt_off_for_install_kvm_on_ppc64(self):
        password = "123secure"
        self.patch(vendor_data, "_generate_password").return_value = password
        node = factory.make_Node(
            status=NODE_STATUS.DEPLOYING,
            osystem="ubuntu",
            netboot=False,
            architecture="ppc64el/generic",
            register_vmhost=True,
        )
        config = list(generate_kvm_pod_configuration(node))
        self.assertIn(
            (
                "write_files",
                [
                    {
                        "path": "/etc/rc.local",
                        "content": (
                            "#!/bin/sh\n"
                            "# This file was generated by MAAS to disable SMT "
                            "on PPC64EL since\n"
                            "# VMs are not supported otherwise.\n"
                            "ppc64_cpu --smt=off\n"
                            "exit 0\n"
                        ),
                        "permissions": "0755",
                    },
                ],
            ),
            config,
        )
        self.assertIn(("runcmd", ["/etc/rc.local"]), config)

    def test_enables_vnic_characteristics_on_s390x(self):
        password = "123secure"
        self.patch(vendor_data, "_generate_password").return_value = password
        node = factory.make_Node(
            status=NODE_STATUS.DEPLOYING,
            osystem="ubuntu",
            netboot=False,
            architecture="s390x/generic",
            register_vmhost=True,
        )
        config = list(generate_kvm_pod_configuration(node))
        self.assertIn(
            (
                "write_files",
                [
                    {
                        "path": "/etc/rc.local",
                        "content": (
                            "#!/bin/bash\n"
                            "# This file was generated by MAAS to enable VNIC "
                            "characteristics to allow\n"
                            "# packets to be forwarded over a bridge.\n"
                            'for bridge in $(bridge link show | awk -F"[ :]" '
                            "'{ print $3 }'); do\n"
                            "    # Isolated networks are not associated with "
                            "a qeth and do not need\n"
                            "    # anything enabled. Ignore them.\n"
                            "    phy_addr=$(lsqeth $bridge 2>/dev/null | "
                            "awk -F ': ' '/cdev0/ {print $2}')\n"
                            '    if [ -n "$phy_addr" ]; then\n'
                            "        chzdev $phy_addr vnicc/learning=1\n"
                            "    fi\n"
                            "done\n"
                        ),
                        "permissions": "0755",
                    },
                ],
            ),
            config,
        )
        self.assertIn(("runcmd", ["/etc/rc.local"]), config)


class TestGenerateEphemeralNetplanLockRemoval(MAASServerTestCase):
    def test_does_nothing_if_deploying(self):
        # MAAS transitions a machine from DEPLOYING to DEPLOYED after
        # user_data has been requested. Make sure deploying nodes don't
        # get this config.
        node = factory.make_Node(status=NODE_STATUS.DEPLOYING)
        config = list(generate_ephemeral_netplan_lock_removal(node))
        self.assertEqual(config, [])

    def test_removes_lock_when_ephemeral(self):
        node = factory.make_Node(
            status=random.choice(COMMISSIONING_LIKE_STATUSES)
        )
        config = list(generate_ephemeral_netplan_lock_removal(node))
        self.assertEqual(config, [("runcmd", ["rm -rf /run/netplan"])])


class TestGenerateEphemeralDeploymentNetworkConfiguration(MAASServerTestCase):
    def test_yields_nothing_when_node_is_not_ephemeral_deployment(self):
        node = factory.make_Node()
        config = list(
            generate_ephemeral_deployment_network_configuration(node)
        )
        self.assertEqual(config, [])

    def test_yields_configuration_when_node_is_ephemeral_deployment(self):
        node = factory.make_Node(
            with_boot_disk=False,
            ephemeral_deploy=True,
            status=NODE_STATUS.DEPLOYING,
        )
        config = list(
            generate_ephemeral_deployment_network_configuration(node)
        )
        self.assertEqual(
            config,
            [
                (
                    "write_files",
                    [
                        {
                            "path": "/etc/netplan/50-maas.yaml",
                            "content": yaml.safe_dump(
                                {"network": {"version": 2}}
                            ),
                        },
                    ],
                ),
                ("runcmd", ["rm -rf /run/netplan", "netplan apply --debug"]),
            ],
        )


class TestGenerateVcenterConfiguration(MAASServerTestCase):
    def test_does_nothing_if_not_vmware(self):
        mock_get_configs = self.patch(Config.objects, "get_configs")
        node = factory.make_Node(
            status=NODE_STATUS.DEPLOYING, owner=factory.make_admin()
        )
        config = get_vendor_data(node, None)
        self.assertThat(mock_get_configs, MockNotCalled())
        self.assertNotIn("write_files", config)

    def test_returns_nothing_if_no_values_set(self):
        node = factory.make_Node(
            status=NODE_STATUS.DEPLOYING,
            osystem="esxi",
            owner=factory.make_admin(),
        )
        node.nodemetadata_set.create(key="vcenter_registration", value="True")
        config = get_vendor_data(node, None)
        self.assertNotIn("write_files", config)

    def test_returns_vcenter_yaml(self):
        node = factory.make_Node(
            status=NODE_STATUS.DEPLOYING,
            osystem="esxi",
            owner=factory.make_admin(),
        )
        node.nodemetadata_set.create(key="vcenter_registration", value="True")
        vcenter = {
            "vcenter_datacenter": factory.make_name("vcenter_datacenter"),
            "vcenter_server": factory.make_name("vcenter_server"),
            "vcenter_password": factory.make_name("vcenter_password"),
            "vcenter_username": factory.make_name("vcenter_username"),
        }
        for key, value in vcenter.items():
            Config.objects.set_config(key, value)
        config = get_vendor_data(node, None)
        self.assertEqual(
            config["write_files"],
            [
                {
                    "content": yaml.safe_dump(vcenter),
                    "path": "/altbootbank/maas/vcenter.yaml",
                },
            ],
        )

    def test_returns_vcenter_yaml_if_rbac_admin(self):
        rbac = self.useFixture(RBACEnabled())
        node = factory.make_Node(
            status=NODE_STATUS.DEPLOYING,
            osystem="esxi",
            owner=factory.make_User(),
        )
        node.nodemetadata_set.create(key="vcenter_registration", value="True")
        rbac.store.add_pool(node.pool)
        rbac.store.allow(node.owner.username, node.pool, "admin-machines")
        vcenter = {
            "vcenter_datacenter": factory.make_name("vcenter_datacenter"),
            "vcenter_server": factory.make_name("vcenter_server"),
            "vcenter_password": factory.make_name("vcenter_password"),
            "vcenter_username": factory.make_name("vcenter_username"),
        }
        for key, value in vcenter.items():
            Config.objects.set_config(key, value)
        config = get_vendor_data(node, None)
        self.assertEqual(
            config["write_files"],
            [
                {
                    "content": yaml.safe_dump(vcenter),
                    "path": "/altbootbank/maas/vcenter.yaml",
                },
            ],
        )

    def test_returns_nothing_if_rbac_user(self):
        rbac = self.useFixture(RBACEnabled())
        node = factory.make_Node(
            status=NODE_STATUS.DEPLOYING,
            osystem="esxi",
            owner=factory.make_User(),
        )
        node.nodemetadata_set.create(key="vcenter_registration", value="True")
        rbac.store.add_pool(node.pool)
        rbac.store.allow(node.owner.username, node.pool, "deploy-machines")
        vcenter = {
            "vcenter_datacenter": factory.make_name("vcenter_datacenter"),
            "vcenter_password": factory.make_name("vcenter_password"),
            "vcenter_server": factory.make_name("vcenter_server"),
            "vcenter_username": factory.make_name("vcenter_username"),
        }
        for key, value in vcenter.items():
            Config.objects.set_config(key, value)
        config = get_vendor_data(node, None)
        self.assertNotIn("write_files", config)

    def test_returns_nothing_if_no_user(self):
        node = factory.make_Node(status=NODE_STATUS.DEPLOYING, osystem="esxi")
        for i in ["datacenter", "password", "server", "username"]:
            key = "vcenter_%s" % i
            Config.objects.set_config(key, factory.make_name(key))
        config = get_vendor_data(node, None)
        self.assertNotIn("write_files", config)

    def test_returns_nothing_if_user(self):
        node = factory.make_Node(
            status=NODE_STATUS.DEPLOYING,
            osystem="esxi",
            owner=factory.make_User(),
        )
        for i in ["server", "username", "password", "datacenter"]:
            key = "vcenter_%s" % i
            Config.objects.set_config(key, factory.make_name(key))
        config = get_vendor_data(node, None)
        self.assertNotIn("write_files", config)

    def test_returns_nothing_if_vcenter_registration_not_set(self):
        node = factory.make_Node(
            status=NODE_STATUS.DEPLOYING,
            osystem="esxi",
            owner=factory.make_admin(),
        )
        for i in ["server", "username", "password", "datacenter"]:
            key = "vcenter_%s" % i
            Config.objects.set_config(key, factory.make_name(key))
        config = get_vendor_data(node, None)
        self.assertNotIn("write_files", config)


class TestGenerateHardwareSyncSystemdConfiguration(MAASServerTestCase):
    def _get_timer_template(self):
        return tempita.Template(
            _get_metadataserver_template(HARDWARE_SYNC_TIMER_TEMPLATE),
        )

    def _get_service_template(self):
        return tempita.Template(
            _get_metadataserver_template(HARDWARE_SYNC_SERVICE_TEMPLATE),
        )

    def test_returns_nothing_if_node_enable_hw_sync_is_False(self):
        node = factory.make_Node(
            status=NODE_STATUS.DEPLOYING,
        )
        config = generate_hardware_sync_systemd_configuration(node)
        self.assertRaises(StopIteration, next, config)

    def test_returns_timer_and_service_when_node_enable_hw_sync_is_True(self):
        node = factory.make_Node(
            status=NODE_STATUS.DEPLOYING,
            enable_hw_sync=True,
        )
        node.boot_cluster_ip = factory.make_ip_address()
        node.save()
        config = generate_hardware_sync_systemd_configuration(node)
        expected_interval = Config.objects.get_config("hardware_sync_interval")

        maas_url = get_node_rack_url(node)

        expected = (
            "write_files",
            [
                {
                    "content": self._get_timer_template().substitute(
                        hardware_sync_interval=systemd_interval_to_calendar(
                            expected_interval
                        )
                    ),
                    "path": "/lib/systemd/system/maas_hardware_sync.timer",
                },
                {
                    "content": self._get_service_template().substitute(
                        admin_token=_get_node_admin_token(node),
                        maas_url=maas_url,
                        system_id=node.system_id,
                        token_file_path=HARDWARE_SYNC_MACHINE_TOKEN_PATH,
                    ),
                    "path": "/lib/systemd/system/maas_hardware_sync.service",
                },
            ],
        )

        self.assertCountEqual(next(config), expected)


class TestGetNodeMAASURL(MAASServerTestCase):
    def test_maas_url_uses_boot_rack_controller(self):
        subnet = factory.make_Subnet()
        rack_controller = factory.make_RackController()
        factory.make_Interface(node=rack_controller, subnet=subnet)
        node = factory.make_Node()
        factory.make_Interface(node=node, subnet=subnet)

        expected_url = (
            f"http://{get_maas_facing_server_host(rack_controller)}:5240/MAAS"
        )
        self.assertEqual(expected_url, get_node_maas_url(node))


class TestGetNodeRackURL(MAASServerTestCase):
    def test_url_uses_machine_facing_rack_controller(self):
        vlan1 = factory.make_VLAN()
        vlan2 = factory.make_VLAN()
        subnet1 = factory.make_Subnet(vlan=vlan1, cidr="10.0.0.0/24")
        subnet2 = factory.make_Subnet(vlan=vlan2, cidr="10.0.1.0/24")
        rack_controller = factory.make_RackController()
        factory.make_Interface(
            node=rack_controller,
            vlan=vlan1,
            subnet=subnet1,
            ip="10.0.0.1",
            link_connected=True,
        )
        factory.make_Interface(
            node=rack_controller,
            vlan=vlan2,
            subnet=subnet2,
            ip="10.0.1.1",
            link_connected=True,
        )
        node = factory.make_Node(
            boot_interface=factory.make_Interface(
                vlan=vlan1, ip="10.0.0.2", subnet=subnet1, link_connected=True
            )
        )
        node.boot_cluster_ip = "10.0.0.1"
        node.save()

        expected_url = "http://10.0.0.1:5248/MAAS"
        self.assertEqual(expected_url, get_node_rack_url(node))
