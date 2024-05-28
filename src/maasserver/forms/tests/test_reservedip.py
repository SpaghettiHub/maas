from maasserver.forms.reservedip import ReservedIPForm
from maasserver.testing.factory import factory
from maasserver.testing.testcase import MAASServerTestCase


class TestReservedIPForm(MAASServerTestCase):
    def test_empty_form_fails_validation(self):
        data = {}

        form = ReservedIPForm(data)

        assert not form.is_valid()
        assert form.errors == {
            "ip": ["This field is required."],
            "subnet": ["This field is required."],
        }

    def test_form_requires_ip(self):
        data = {
            "subnet": factory.make_Subnet(cidr="10.0.0.0/24"),
            "mac_address": factory.make_mac_address(),
            "comment": factory.make_name("comment"),
        }

        form = ReservedIPForm(data)

        assert not form.is_valid()
        assert form.errors == {"ip": ["This field is required."]}

    def test_form_requires_subnet(self):
        data = {
            "ip": "10.0.0.15",
            "mac_address": factory.make_mac_address(),
            "comment": factory.make_name("comment"),
        }

        form = ReservedIPForm(data)

        assert not form.is_valid()
        assert form.errors == {"subnet": ["This field is required."]}

    def test_subnet_is_optional_if_it_can_be_found(self):
        subnet = factory.make_Subnet(cidr="10.0.0.0/24")
        data = {
            "ip": "10.0.0.15",
            "mac_address": factory.make_mac_address(),
            "comment": factory.make_name("comment"),
        }

        form = ReservedIPForm(data)

        assert form.is_valid()
        reservedip = form.save()
        assert reservedip.subnet == subnet

    def test_mac_address_is_optional(self):
        data = {
            "ip": "10.0.0.15",
            "subnet": factory.make_Subnet(cidr="10.0.0.0/24"),
            "comment": factory.make_name("comment"),
        }

        form = ReservedIPForm(data)

        assert form.is_valid()
        reservedip = form.save()
        assert reservedip.mac_address == ""

    def test_comment_is_optional(self):
        data = {
            "ip": "10.0.0.15",
            "subnet": factory.make_Subnet(cidr="10.0.0.0/24"),
            "mac_address": factory.make_mac_address(),
        }

        form = ReservedIPForm(data)

        assert form.is_valid()
        reservedip = form.save()
        assert reservedip.comment == ""
