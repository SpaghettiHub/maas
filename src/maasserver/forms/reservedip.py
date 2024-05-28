# Copyright 2024 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Reserved IP form."""

from maasserver.forms import MAASModelForm
from maasserver.models import ReservedIP, Subnet


class ReservedIPForm(MAASModelForm):
    """ReservedIp creation/edition form."""

    class Meta:
        model = ReservedIP
        fields = ("ip", "subnet", "mac_address", "comment")

    def __init__(self, data: dict | None, request=None, *args, **kwargs):
        data = {} if data is None else data.copy()

        ip = data.get("ip")
        subnet_id = data.get("subnet")

        if ip is not None and subnet_id is None:
            if (
                subnet := Subnet.objects.get_best_subnet_for_ip(ip)
            ) is not None:
                data["subnet"] = subnet.id

        super().__init__(data=data, *args, **kwargs)
