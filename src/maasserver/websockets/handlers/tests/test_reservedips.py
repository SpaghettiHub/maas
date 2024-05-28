# Copyright 2024 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests the ReservedIP WebSocket handler"""


from maasserver.models.reservedip import ReservedIP
from maasserver.testing.factory import factory
from maasserver.testing.testcase import MAASServerTestCase
from maasserver.websockets.handlers.reservedip import ReservedIPHandler


class TestReservedIPHandler(MAASServerTestCase):
    def test_create(self):
        user = factory.make_User()
        subnet = factory.make_Subnet(cidr="10.0.0.0/24")
        handler = ReservedIPHandler(user, {}, None)

        reserved_ip = handler.create(
            {
                "ip": "10.0.0.55",
                "mac_address": "00:11:22:33:44:55",
                "comment": "this is a comment",
            }
        )

        assert reserved_ip["ip"] == "10.0.0.55"
        assert reserved_ip["subnet"] == subnet.id
        assert reserved_ip["mac_address"] == "00:11:22:33:44:55"
        assert reserved_ip["comment"] == "this is a comment"

    def test_get(self):
        user = factory.make_User()
        factory.make_Subnet(cidr="10.0.0.0/24")
        handler = ReservedIPHandler(user, {}, None)

        reserved_ip = handler.create({"ip": "10.0.0.16"})

        model_entry = ReservedIP.objects.get(id=reserved_ip["id"])
        assert model_entry.subnet.cidr == "10.0.0.0/24"
        assert model_entry.ip == "10.0.0.16"
        assert model_entry.mac_address == ""
        assert model_entry.comment == ""

    def test_update(self):
        user = factory.make_User()
        factory.make_Subnet(cidr="10.0.0.0/24")
        handler = ReservedIPHandler(user, {}, None)
        reserved_ip = handler.create({"ip": "10.0.0.16"})

        reserved_ip["mac_address"] = "00:11:22:33:44:55"
        reserved_ip["comment"] = "test ip and mac address"
        handler.update(reserved_ip)

        model_entry = ReservedIP.objects.get(id=reserved_ip["id"])
        assert model_entry.subnet.cidr == "10.0.0.0/24"
        assert model_entry.ip == "10.0.0.16"
        assert model_entry.mac_address == "00:11:22:33:44:55"
        assert model_entry.comment == "test ip and mac address"

    def test_delete(self):
        user = factory.make_User()
        factory.make_Subnet(cidr="10.0.0.0/24")
        handler = ReservedIPHandler(user, {}, None)
        reserved_ip = handler.create({"ip": "10.0.0.16"})

        assert ReservedIP.objects.all()
        handler.delete({"id": reserved_ip["id"]})
        assert not ReservedIP.objects.all()

    def test_list(self):
        user = factory.make_User()
        factory.make_Subnet(cidr="10.0.0.0/24")
        handler = ReservedIPHandler(user, {}, None)

        reserved_ips = handler.list({})
        assert not reserved_ips

        handler.create({"ip": "10.0.0.16"})
        handler.create({"ip": "10.0.0.25"})
        reserved_ips = handler.list({})
        assert len(reserved_ips) == 2
        assert sorted(r["ip"] for r in reserved_ips) == [
            "10.0.0.16",
            "10.0.0.25",
        ]
