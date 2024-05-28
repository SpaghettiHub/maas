# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests of the ReservedIP model."""

from django.core.exceptions import ValidationError
import pytest

from maasserver.models import Subnet
from maasserver.models.reservedip import ReservedIP
from maasserver.testing.factory import factory
from maasserver.testing.testcase import MAASServerTestCase


def make_subnet() -> Subnet:
    """Create a subnet for testing the ReservedIp model."""
    return factory.make_Subnet(
        cidr="192.168.0.0/24", gateway_ip="192.168.0.1", dns_servers=[]
    )


class TestReservedIP(MAASServerTestCase):
    """Test class for the ReservedIp model."""

    def test_create_requires_a_valid_ip_address(self):
        subnet = make_subnet()

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

    def test_create_requires_a_valid_mac_address(self):
        subnet = make_subnet()

        reserved_ip = ReservedIP(
            ip="192.168.0.10",
            subnet=subnet,
            mac_address=None,
            comment="Test: creating a reserved IP",
        )
        reserved_ip.clean_fields()

        msgs = [
            "'00:11:22:33:44:gg' is not a valid MAC address.",
            "'0011:22:33:44:gg' is not a valid MAC address.",
        ]
        for ip_value, mac_value, msg in [
            ("192.168.0.11", "00:11:22:33:44:gg", {"mac_address": [msgs[0]]}),
            ("192.168.0.15", "0011:22:33:44:gg", {"mac_address": [msgs[1]]}),
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

    def test_ip_in_subnet(self):
        subnet = make_subnet()

        reserved_ip = ReservedIP(
            ip="192.168.1.10",
            subnet=subnet,
            mac_address=None,
        )
        with pytest.raises(Exception) as exc_info:
            reserved_ip.clean()

        msg = ["192.168.1.10 is not in subnet 192.168.0.0/24"]
        assert exc_info.value.message_dict == {("ip", "subnet"): msg}

    def test_ip_has_not_been_reserved_yet(self):
        subnet = make_subnet()

        reserved_ip_1 = ReservedIP(
            ip="192.168.0.10",
            subnet=subnet,
            mac_address=None,
        )
        reserved_ip_2 = ReservedIP(
            ip="192.168.0.10",
            subnet=subnet,
            mac_address=None,
        )
        reserved_ip_1.save()
        with pytest.raises(Exception) as exc_info:
            reserved_ip_2.save()

        msg = ["192.168.0.10 is already a reserved IP address."]
        assert exc_info.value.message_dict == {"ip": msg}
