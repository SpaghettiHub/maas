from maasservicelayer.models.base import MaasTimestampedBaseModel


class DNSResource(MaasTimestampedBaseModel):
    name: str
    address_ttl: int
