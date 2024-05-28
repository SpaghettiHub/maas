from maasserver.api.support import OperationsHandler
from maasserver.models import ReservedIP


class ReservedIPHandler(OperationsHandler):
    api_doc_section_name = "Reserved IP"

    model = ReservedIP

    field = (
        "ip",
        "mac_address",
    )

    @classmethod
    def resource_uri(cls, *args, **kwargs):
        # See the comment in NodeHandler.resource_uri.
        return ("reservedip_handler", [])

    def read(self, request):
        return {"value": "key"}
