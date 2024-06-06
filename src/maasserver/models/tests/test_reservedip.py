# Copyright 2024 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests of the ReservedIP model."""

from django.core.exceptions import ValidationError
import pytest

from maasserver.models.reservedip import ReservedIP
from maasserver.testing.factory import factory
from maasserver.testing.testcase import MAASServerTestCase


class TestReservedIP(MAASServerTestCase):
    """Test class for the ReservedIp model."""

    def setUp(self):
        super().setUp()
        self.subnet_ipv4 = factory.make_Subnet(
            cidr="192.168.0.0/24", gateway_ip="192.168.0.1", dns_servers=[]
        )
        self.subnet_ipv6 = factory.make_Subnet(
            cidr="2001::/64", gateway_ip="2001::1", dns_servers=[]
        )

    def test_create_reserved_ipv4(self):
        subnet = self.subnet_ipv4

        reserved_ip = ReservedIP(
            ip="192.168.0.15",
            subnet=subnet,
            mac_address="00:11:22:33:44:55",
            comment="this is a comment",
        )
        reserved_ip.clean_fields()

        assert reserved_ip.ip == "192.168.0.15"
        assert reserved_ip.subnet.cidr == "192.168.0.0/24"
        assert reserved_ip.mac_address == "00:11:22:33:44:55"
        assert reserved_ip.comment == "this is a comment"

    def test_create_reserved_ipv6(self):
        subnet = self.subnet_ipv6

        reserved_ip = ReservedIP(
            ip="2001::45",
            subnet=subnet,
            mac_address="00:11:22:33:44:55",
            comment="this is a comment",
        )
        reserved_ip.clean_fields()

        assert reserved_ip.ip == "2001::45"
        assert reserved_ip.subnet.cidr == "2001::/64"
        assert reserved_ip.mac_address == "00:11:22:33:44:55"
        assert reserved_ip.comment == "this is a comment"

    def test_create_requires_a_valid_ip_address(self):
        subnet = self.subnet_ipv4

        msgs = (
            "This field cannot be null.",
            "Enter a valid IPv4 or IPv6 address.",
        )
        for value, msg in [
            (None, {"ip": [msgs[0]]}),
            ("192.168.x.10", {"ip": [msgs[1]]}),
        ]:
            reserved_ip = ReservedIP(
                ip=value,
                subnet=subnet,
                mac_address="00:11:22:33:44:55",
                comment="Test: creating a reserved IP",
            )

            with pytest.raises(ValidationError) as exc_info:
                reserved_ip.clean_fields()
            assert exc_info.value.message_dict == msg

    def test_create_requires_ip_address_has_not_been_reserved(self):
        subnet = self.subnet_ipv4

        ReservedIP(
            ip="192.168.0.15",
            subnet=subnet,
        ).save()

        with pytest.raises(ValidationError) as exc_info:
            ReservedIP(
                ip="192.168.0.15",
                subnet=subnet,
            ).save()
        assert exc_info.value.message_dict == {
            "ip": ["Reserved IP with this IP address already exists."]
        }

    def test_create_requires_mac_address_has_not_been_reserved(self):
        subnet = self.subnet_ipv4

        ReservedIP(
            ip="192.168.0.15",
            subnet=subnet,
            mac_address="00:11:22:33:44:55",
        ).save()

        with pytest.raises(ValidationError) as exc_info:
            ReservedIP(
                ip="192.168.0.16",
                subnet=subnet,
                mac_address="00:11:22:33:44:55",
            ).save()

        assert exc_info.value.message_dict == {
            "mac_address": [
                "Reserved IP with this MAC address already exists."
            ]
        }

    def test_create_requires_a_subnet(self):
        reserved_ip = ReservedIP(
            ip="192.168.0.10",
            mac_address="00:11:22:33:44:55",
            comment="Test: creating a reserved IP",
        )
        with pytest.raises(ValidationError) as exc_info:
            reserved_ip.clean_fields()

        assert exc_info.value.message_dict == {
            "subnet": ["This field cannot be null."]
        }

    def test_create_requires_ip_within_subnet(self):
        subnet = self.subnet_ipv4
        reserved_ip = ReservedIP(
            ip="192.168.1.10",
            subnet=subnet,
            mac_address="00:11:22:33:44:55",
            comment="Test: creating a reserved IP",
        )

        with pytest.raises(ValidationError) as exc_info:
            reserved_ip.clean()

        assert exc_info.value.message_dict == {
            ("ip", "subnet"): ["192.168.1.10 is not in subnet 192.168.0.0/24"]
        }

    def test_create_requires_ip_not_to_be_broadcast_address(self):
        subnet = self.subnet_ipv4
        reserved_ip = ReservedIP(
            ip="192.168.0.255",
            subnet=subnet,
            mac_address="00:11:22:33:44:55",
            comment="Test: creating a reserved IP",
        )

        with pytest.raises(ValidationError) as exc_info:
            reserved_ip.clean()

        assert exc_info.value.message_dict == {
            "subnet": ["Broadcast address cannot be used as reserved IP."]
        }

    def test_create_requires_ip_not_to_be_network_address(self):
        subnet = self.subnet_ipv4
        reserved_ip = ReservedIP(
            ip="192.168.0.0",
            subnet=subnet,
            mac_address="00:11:22:33:44:55",
            comment="Test: creating a reserved IP",
        )

        with pytest.raises(ValidationError) as exc_info:
            reserved_ip.clean()

        assert exc_info.value.message_dict == {
            "subnet": [
                "Reserved network address cannot be included in IP range."
            ]
        }

    def test_create_requires_ip_not_to_be_anycast_address(self):
        subnet = self.subnet_ipv6
        reserved_ip = ReservedIP(
            ip="2001::",
            subnet=subnet,
            mac_address="00:11:22:33:44:55",
            comment="Test: creating a reserved IP",
        )

        with pytest.raises(ValidationError) as exc_info:
            reserved_ip.clean()

        assert exc_info.value.message_dict == {
            "subnet": [
                "Reserved network address cannot be included in IP range."
            ]
        }

    def test_create_requires_a_valid_mac_address(self):
        subnet = self.subnet_ipv4

        # valid MAC address
        ReservedIP(
            ip="192.168.0.10",
            subnet=subnet,
            mac_address=None,
        ).clean_fields()
        ReservedIP(
            ip="192.168.0.10",
            subnet=subnet,
            mac_address="00:11:22:33:44:55",
        ).clean_fields()

        # invalid MAC address
        msgs = [
            "'00:11:22:33:44:gg' is not a valid MAC address.",
            "'0011:22:33:44:55' is not a valid MAC address.",
        ]
        for ip_value, mac_value, msg in [
            ("192.168.0.11", "00:11:22:33:44:gg", {"mac_address": [msgs[0]]}),
            ("192.168.0.15", "0011:22:33:44:55", {"mac_address": [msgs[1]]}),
        ]:
            reserved_ip = ReservedIP(
                ip=ip_value,
                subnet=subnet,
                mac_address=mac_value,
                comment="Test: creating a reserved IP",
            )

            with pytest.raises(ValidationError) as exc_info:
                reserved_ip.clean_fields()
            assert exc_info.value.message_dict == msg

    def test_ip_is_in_subnet(self):
        subnet = self.subnet_ipv4

        reserved_ip = ReservedIP(
            ip="192.168.1.10",
            subnet=subnet,
            mac_address=None,
        )
        with pytest.raises(Exception) as exc_info:
            reserved_ip.clean()

        msg = ["192.168.1.10 is not in subnet 192.168.0.0/24"]
        assert exc_info.value.message_dict == {("ip", "subnet"): msg}

    def test_reserved_ip_to_str(self):
        subnet = self.subnet_ipv4

        assert (
            str(
                ReservedIP(
                    ip="192.168.0.55",
                    subnet=subnet,
                    mac_address=None,
                )
            )
            == "192.168.0.55 (192.168.0.0/24)"
        )

        assert (
            str(
                ReservedIP(
                    ip="192.168.0.55",
                    subnet=subnet,
                    mac_address="00:11:22:33:44:55",
                )
            )
            == "192.168.0.55 (192.168.0.0/24), 00:11:22:33:44:55"
        )

        assert (
            str(
                ReservedIP(
                    ip="192.168.0.55",
                    subnet=subnet,
                    mac_address=None,
                    comment="this is a comment.",
                )
            )
            == "192.168.0.55 (192.168.0.0/24), this is a comment."
        )

        assert (
            str(
                ReservedIP(
                    ip="192.168.0.55",
                    subnet=subnet,
                    mac_address="00:11:22:33:44:55",
                    comment="this is a comment.",
                )
            )
            == "192.168.0.55 (192.168.0.0/24), 00:11:22:33:44:55, this is a comment."
        )
