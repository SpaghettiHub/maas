# Copyright 2024 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Model definition for reserved IPs.

The ReservedIP model allows a user to reserve an IP for a specific purpose.
The IP:
- remains reserved unless the user release it,
- can be linked to a mac address.
"""
from django.core.exceptions import ValidationError
from django.db.models import (
    CASCADE,
    CharField,
    ForeignKey,
    Manager,
    TextField,
    UniqueConstraint,
)
from django.db.models.fields import GenericIPAddressField
from netaddr import IPAddress, IPNetwork

from maasserver.fields import MAC_VALIDATOR
from maasserver.models.cleansave import CleanSave
from maasserver.models.timestampedmodel import TimestampedModel
from maasserver.utils.orm import transactional


class ReservedIPManager(Manager):
    """Manager of the ReservedIP model.

    As (Django) manager, this class interfaces with the ReservedIp model in the
    database.
    """


class ReservedIP(CleanSave, TimestampedModel):
    """Reserved IP model.

    (Django) model containing the fields and behaviours of the reserved IPs
    data.
    """

    objects = ReservedIPManager()

    subnet = ForeignKey(
        "Subnet", editable=True, blank=False, null=False, on_delete=CASCADE
    )

    ip = GenericIPAddressField(
        null=False, editable=True, blank=False, verbose_name="IP address"
    )

    mac_address = TextField(
        null=True,
        blank=True,
        validators=[MAC_VALIDATOR],
        verbose_name="MAC address",
    )

    comment = CharField(
        max_length=255, null=True, blank=True, editable=True, default=""
    )

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["ip"], name="maasserver_reservedip_ip_uniq"
            ),
            UniqueConstraint(
                fields=["mac_address"],
                name="maasserver_reservedip_mac_address_uniq",
            ),
        ]
        verbose_name = "Reserved IP"

    def clean(self) -> None:
        if report := self._validate():
            raise ValidationError(report)
        super().clean()

    @transactional
    def _validate(self) -> dict:
        """Validate the fields of the models returning a report as result of
        the validation.
        The report is a dictionary where each key is a field or fields that
        failed the validation, and the value is a message describing the error.
        If the report is empty, the validation passed.
        """
        report = {}
        ip = IPAddress(self.ip)
        cidr = IPNetwork(self.subnet.cidr)

        if r_ip := ReservedIP.objects.filter(ip=str(ip)):
            r_ip = r_ip[0]
            if r_ip.ip != self.ip:
                report["ip"] = f"{ip} is already a reserved IP address."
        else:
            if ip not in cidr:
                report["ip", "subnet"] = f"{ip} is not in subnet {cidr}"

        if not report:
            if cidr.network == ip:
                report[
                    "subnet"
                ] = "Reserved network address cannot be included in IP range."
            elif cidr.version == 4 and cidr.broadcast == ip:
                report[
                    "subnet"
                ] = "Broadcast address cannot be used as reserved IP."

        return report

    def __str__(self):
        fields = [
            f"{self.ip} ({self.subnet.cidr})",
            self.mac_address,
            self.comment,
        ]
        return ", ".join(filter(None, fields))
