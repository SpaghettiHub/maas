# Copyright 2024 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""The Reserved IP handler for the WebSocket connection"""

from django.db.models.query import QuerySet

from maasserver.forms.reservedip import ReservedIPForm
from maasserver.models import ReservedIP
from maasserver.websockets.handlers.timestampedmodel import (
    TimestampedModelHandler,
)


class ReservedIPHandler(TimestampedModelHandler):
    class Meta:
        queryset: QuerySet = ReservedIP.objects.all().select_related("subnet")
        pk: str = "id"
        form: ReservedIPForm = ReservedIPForm
        allowed_methods: list[str] = [
            "create",
            "update",
            "delete",
            "get",
            "list",
        ]
