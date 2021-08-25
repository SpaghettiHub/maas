# Copyright 2016-2021 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""vendor-data for cloud-init's use."""


from base64 import b64encode
from crypt import crypt
from itertools import chain
from os import urandom
from textwrap import dedent

from netaddr import IPAddress
import yaml

from maasserver import ntp
from maasserver.models import Config, NodeMetadata
from maasserver.models.controllerinfo import get_target_version
from maasserver.node_status import COMMISSIONING_LIKE_STATUSES
from maasserver.permissions import NodePermission
from maasserver.preseed import get_network_yaml_settings
from maasserver.preseed_network import NodeNetworkConfiguration
from maasserver.server_address import get_maas_facing_server_host
from provisioningserver.ntp.config import normalise_address
from provisioningserver.utils.text import make_gecos_field

LXD_PASSWORD_METADATA_KEY = "lxd_password"
VIRSH_PASSWORD_METADATA_KEY = "virsh_password"


def get_vendor_data(node, proxy):
    generators = (
        generate_system_info(node),
        generate_snap_configuration(node, proxy),
        generate_ntp_configuration(node),
        generate_rack_controller_configuration(node),
        generate_kvm_pod_configuration(node),
        generate_ephemeral_netplan_lock_removal(node),
        generate_ephemeral_deployment_network_configuration(node),
        generate_vcenter_configuration(node),
    )
    vendor_data = {}
    for key, value in chain(*generators):
        # some keys can be returned by different generators. In that case,
        # collect entries from each generator.
        if key in ("runcmd", "write_files"):
            vendor_data.setdefault(key, []).extend(value)
        else:
            assert (
                key not in vendor_data
            ), f"vendor-data key {key} already in configuration"
            vendor_data[key] = value
    return vendor_data


def generate_system_info(node):
    """Generate cloud-init system information for the given node."""
    if node.owner is not None and node.default_user:
        username = node.default_user
        fullname = node.owner.get_full_name()
        gecos = make_gecos_field(fullname)
        yield "system_info", {
            "default_user": {"name": username, "gecos": gecos}
        }


def generate_snap_configuration(node, proxy):
    """Generate cloud-init configuration for snapd."""
    if not proxy:
        return
    yield "snap", {
        "commands": [
            f'snap set system proxy.http="{proxy}" proxy.https="{proxy}"',
        ],
    }


def generate_ntp_configuration(node):
    """Generate cloud-init configuration for NTP servers.

    cloud-init supports::

      ntp:
        pools:
          - 0.mypool.pool.ntp.org
          - 1.myotherpool.pool.ntp.org
        servers:
          - 102.10.10.10
          - ntp.ubuntu.com

    MAAS assumes that IP addresses are "servers" and hostnames/FQDNs "pools".
    """
    ntp_servers = ntp.get_servers_for(node)
    if not ntp_servers:
        return
    # Separate out IP addresses from the rest.
    addrs, other = set(), set()
    for ntp_server in map(normalise_address, ntp_servers):
        bucket = addrs if isinstance(ntp_server, IPAddress) else other
        bucket.add(ntp_server)
    servers = [addr.format() for addr in sorted(addrs)]
    pools = sorted(other)  # Hostnames and FQDNs only.
    yield "ntp", {"servers": servers, "pools": pools}


def generate_rack_controller_configuration(node):
    """Generate cloud-init configuration to install the rack controller."""
    # To determine this is a machine that's accessing the metadata after
    # initial deployment, we use 'node.netboot'. This flag is set to off after
    # curtin has installed the operating system and before the machine reboots
    # for the first time.
    if (
        not node.netboot
        and node.install_rackd
        and node.osystem in ("ubuntu", "ubuntu-core")
    ):
        hostname = get_maas_facing_server_host(node.get_boot_rack_controller())
        maas_url = f"http://{hostname}:5240/MAAS"
        secret = Config.objects.get_config("rpc_shared_secret")
        channel = str(get_target_version().snap_channel)
        yield "runcmd", [
            f"snap install maas --channel={channel}",
            f"/snap/bin/maas init rack --maas-url {maas_url} --secret {secret}",
        ]


def generate_ephemeral_netplan_lock_removal(node):
    """Remove netplan's interface lock.

    When booting a machine over the network netplan creates a configuration
    file in /run/netplan for the interface used to boot. This contains the
    settings used on boot(DHCP), what renderer was used(networkd), and marks
    the interface as critical. Netplan will ensure interfaces marked critical
    will always have the specified configuration applied. This overrides
    anything put in /etc/netplan breaking custom network configuration."""

    if node.status in COMMISSIONING_LIKE_STATUSES:
        yield "runcmd", ["rm -rf /run/netplan"]


def generate_ephemeral_deployment_network_configuration(node):
    """Generate cloud-init network configuration for ephemeral deployment."""
    if not node.ephemeral_deployment:
        return
    osystem = node.get_osystem()
    release = node.get_distro_series()
    network_yaml_settings = get_network_yaml_settings(osystem, release)
    network_config = NodeNetworkConfiguration(
        node,
        version=network_yaml_settings.version,
        source_routing=network_yaml_settings.source_routing,
    )
    # Render the resulting YAML.
    network_config_yaml = yaml.safe_dump(
        network_config.config, default_flow_style=False
    )
    yield "write_files", [
        {
            "content": network_config_yaml,
            "path": "/etc/netplan/50-maas.yaml",
        }
    ]
    yield "runcmd", ["rm -rf /run/netplan", "netplan apply --debug"]


def generate_kvm_pod_configuration(node):
    """Generate cloud-init configuration to install the node as a KVM pod."""
    if node.netboot or not (node.install_kvm or node.register_vmhost):
        return

    arch, _ = node.split_arch()

    if node.register_vmhost:
        password = _generate_password()
        NodeMetadata.objects.update_or_create(
            node=node,
            key=LXD_PASSWORD_METADATA_KEY,
            defaults={"value": password},
        )
        # When installing LXD, ensure no deb packages are installed, since they
        # would conflict with the snap. Also, ensure that the snap version is
        # the latest, since MAAS requires features not present in the one
        # installed by default in Focal.
        yield "runcmd", [
            "apt autoremove --purge --yes lxd lxd-client lxcfs",
            "snap install lxd --channel=latest",
            "snap refresh lxd --channel=latest",
            f'lxd init --auto --network-address=[::] --trust-password="{password}"',
        ]

    if node.install_kvm:
        password = _generate_password()
        NodeMetadata.objects.update_or_create(
            node=node,
            key=VIRSH_PASSWORD_METADATA_KEY,
            defaults={"value": password},
        )
        # Make sure SSH password authentication is enabled.
        yield "ssh_pwauth", True
        # Create a custom 'virsh' user (in addition to the default user)
        # with the encrypted password, and a locked-down shell.
        yield "users", [
            "default",
            {
                "name": "virsh",
                "lock_passwd": False,
                "passwd": crypt(password),
                "shell": "/bin/rbash",
            },
        ]

        packages = ["libvirt-daemon-system", "libvirt-clients"]
        # libvirt emulates UEFI on ARM64 however qemu-efi-aarch64 is only a
        # suggestion on ARM64 so cloud-init doesn't install it.
        if arch == "arm64":
            packages.append("qemu-efi-aarch64")
        yield "packages", packages

        # set up virsh user and ssh authentication
        yield "runcmd", [
            # Restrict the $PATH so that rbash can be used to limit what the
            # virsh user can do if they manage to get a shell.
            "mkdir -p /home/virsh/bin",
            "ln -s /usr/bin/virsh /home/virsh/bin/virsh",
            # Make sure the 'virsh' user is allowed to access libvirt.
            "/usr/sbin/usermod --append --groups libvirt,libvirt-qemu virsh",
            # SSH needs to be restarted in order for the above changes to take
            # effect.
            "systemctl restart sshd",
        ]

        yield "write_files", [
            {
                "path": "/home/virsh/.bash_profile",
                "content": "PATH=/home/virsh/bin",
            },
            # Use a ForceCommand to make sure the only thing the virsh user can
            # do with SSH is communicate with libvirt.
            {
                "path": "/etc/ssh/sshd_config",
                "content": dedent(
                    """\
                    Match user virsh
                      X11Forwarding no
                      AllowTcpForwarding no
                      PermitTTY no
                      ForceCommand nc -q 0 -U /var/run/libvirt/libvirt-sock
                    """
                ),
                "append": True,
            },
        ]

    if arch == "ppc64el":
        rc_script = dedent(
            """\
            #!/bin/sh
            # This file was generated by MAAS to disable SMT on PPC64EL since
            # VMs are not supported otherwise.
            ppc64_cpu --smt=off
            exit 0
            """
        )
    elif arch == "s390x":
        rc_script = dedent(
            """\
            #!/bin/bash
            # This file was generated by MAAS to enable VNIC characteristics to allow
            # packets to be forwarded over a bridge.
            for bridge in $(bridge link show | awk -F"[ :]" '{ print $3 }'); do
                # Isolated networks are not associated with a qeth and do not need
                # anything enabled. Ignore them.
                phy_addr=$(lsqeth $bridge 2>/dev/null | awk -F ': ' '/cdev0/ {print $2}')
                if [ -n "$phy_addr" ]; then
                    chzdev $phy_addr vnicc/learning=1
                fi
            done
            """
        )
    else:
        rc_script = None

    if rc_script:
        rc_local = "/etc/rc.local"
        yield "write_files", [
            {
                "path": rc_local,
                "content": rc_script,
                "permissions": "0755",
            },
        ]
        yield "runcmd", [rc_local]


def generate_vcenter_configuration(node):
    """Generate vendor config when deploying ESXi."""
    if node.osystem != "esxi":
        # Only return vcenter credentials if vcenter is being deployed.
        return
    if not node.owner or not node.owner.has_perm(NodePermission.admin, node):
        # VMware vCenter credentials are only given to machines deployed by
        # administrators.
        return
    vcenter_registration = NodeMetadata.objects.get(
        node=node, key="vcenter_registration"
    )
    if not vcenter_registration:
        # Only send credentials if told to at deployment time.
        return
    # Only send values that aren't blank.
    configs = {
        key: value
        for key, value in Config.objects.get_configs(
            [
                "vcenter_server",
                "vcenter_username",
                "vcenter_password",
                "vcenter_datacenter",
            ]
        ).items()
        if value
    }
    if configs:
        yield "write_files", [
            {
                "content": yaml.safe_dump(configs),
                "path": "/altbootbank/maas/vcenter.yaml",
            }
        ]


def _generate_password():
    """Generate a 32-character password by encoding 24 bytes as base64."""
    return b64encode(urandom(24), altchars=b".!").decode("ascii")
