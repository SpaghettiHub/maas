# Copyright 2025 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from ipaddress import IPv4Address, IPv6Address
from typing import Optional, Self

from maasapiserver.v3.api.public.models.responses.base import (
    BaseHal,
    BaseHref,
    HalResponse,
    PaginatedResponse,
)
from maasservicelayer.models.dnsresourcerecordsets import (
    AaaaDnsRecord,
    ADnsRecord,
    CnameDnsRecord,
    DnsResourceRecordSet,
    DnsResourceTypeEnum,
    MxDnsRecord,
    NsDnsRecord,
    SrvDnsRecord,
    SshfpDnsRecord,
    TxtDnsRecord,
)
from maasservicelayer.models.domains import Domain


class DomainResponse(HalResponse[BaseHal]):
    kind = "Domain"
    authoritative: bool
    ttl: Optional[int]
    id: int
    name: str
    # TODO: add is_default

    @classmethod
    def from_model(cls, domain: Domain, self_base_hyperlink: str) -> Self:
        return cls(
            authoritative=domain.authoritative,
            ttl=domain.ttl,
            id=domain.id,
            name=domain.name,
            hal_links=BaseHal(
                self=BaseHref(
                    href=f"{self_base_hyperlink.rstrip('/')}/{domain.id}"
                )
            ),
        )


class DomainsListResponse(PaginatedResponse[DomainResponse]):
    kind = "DomainsList"


class ADnsRecordResponse(HalResponse[BaseHal]):
    kind = "ARecord"
    ipv4address: IPv4Address

    @classmethod
    def from_model(cls, a_record: ADnsRecord) -> Self:
        return cls(ipv4address=a_record.address)


class AaaaDnsRecordResponse(HalResponse[BaseHal]):
    kind = "AaaaRecord"
    ipv6address: IPv6Address

    @classmethod
    def from_model(cls, aaaa_record: AaaaDnsRecord) -> Self:
        return cls(ipv6address=aaaa_record.address)


class CnameDnsRecordResponse(HalResponse[BaseHal]):
    kind = "CnameRecord"
    cname: str

    @classmethod
    def from_model(cls, cname_record: CnameDnsRecord) -> Self:
        return cls(cname=cname_record.cname)


class MxDnsRecordResponse(HalResponse[BaseHal]):
    kind = "MxRecord"
    exchange: str
    preference: int

    @classmethod
    def from_model(cls, mx_record: MxDnsRecord) -> Self:
        return cls(
            exchange=mx_record.exchange, preference=mx_record.preference
        )


class NsDnsRecordResponse(HalResponse[BaseHal]):
    kind = "NsRecord"
    nsdname: str

    @classmethod
    def from_model(cls, ns_record: NsDnsRecord) -> Self:
        return cls(nsdname=ns_record.nsdname)


class SshfpDnsRecordResponse(HalResponse[BaseHal]):
    kind = "SshfpRecord"
    algorithm: int
    fingerprint_type: int
    fingerprint: str

    @classmethod
    def from_model(cls, sshfp_record: SshfpDnsRecord) -> Self:
        return cls(
            algorithm=sshfp_record.algorithm,
            fingerprint_type=sshfp_record.fingerprint_type,
            fingerprint=sshfp_record.fingerprint,
        )


class SrvDnsRecordResponse(HalResponse[BaseHal]):
    kind = "SrvRecord"
    port: int
    priority: int
    target: str
    weight: int

    @classmethod
    def from_model(cls, srv_record: SrvDnsRecord) -> Self:
        return cls(
            port=srv_record.port,
            priority=srv_record.priority,
            target=srv_record.target,
            weight=srv_record.weight,
        )


class TxtDnsRecordResponse(HalResponse[BaseHal]):
    kind = "TxtRecord"
    data: str

    @classmethod
    def from_model(cls, txt_record: TxtDnsRecord) -> Self:
        return cls(data=txt_record.txt_data)


class DomainResourceRecordSetResponse(HalResponse[BaseHal]):
    kind = "DomainResourceRecordSet"
    name: str
    node_id: Optional[int]
    ttl: Optional[int]
    rrtype: DnsResourceTypeEnum
    a_records: list[ADnsRecordResponse] | None
    aaaa_records: list[AaaaDnsRecordResponse] | None
    cname_records: list[CnameDnsRecordResponse] | None
    mx_records: list[MxDnsRecordResponse] | None
    ns_records: list[NsDnsRecordResponse] | None
    sshfp_records: list[SshfpDnsRecordResponse] | None
    srv_records: list[SrvDnsRecordResponse] | None
    txt_records: list[TxtDnsRecordResponse] | None

    @classmethod
    def from_model(
        cls,
        rrset: DnsResourceRecordSet,
        self_base_hyperlink: str,
    ) -> Self:
        return cls(
            name=rrset.name,
            node_id=rrset.node_id,
            ttl=rrset.node_id,
            rrtype=rrset.rrtype,
            a_records=[
                ADnsRecordResponse.from_model(r) for r in rrset.a_records
            ]
            if rrset.a_records is not None
            else None,
            aaaa_records=[
                AaaaDnsRecordResponse.from_model(r) for r in rrset.aaaa_records
            ]
            if rrset.aaaa_records is not None
            else None,
            cname_records=[
                CnameDnsRecordResponse.from_model(r)
                for r in rrset.cname_records
            ]
            if rrset.cname_records is not None
            else None,
            mx_records=[
                MxDnsRecordResponse.from_model(r) for r in rrset.mx_records
            ]
            if rrset.mx_records is not None
            else None,
            ns_records=[
                NsDnsRecordResponse.from_model(r) for r in rrset.ns_records
            ]
            if rrset.ns_records is not None
            else None,
            sshfp_records=[
                SshfpDnsRecordResponse.from_model(r)
                for r in rrset.sshfp_records
            ]
            if rrset.sshfp_records is not None
            else None,
            srv_records=[
                SrvDnsRecordResponse.from_model(r) for r in rrset.srv_records
            ]
            if rrset.srv_records is not None
            else None,
            txt_records=[
                TxtDnsRecordResponse.from_model(r) for r in rrset.txt_records
            ]
            if rrset.txt_records is not None
            else None,
            hal_links=BaseHal(
                self=BaseHref(href=f"{self_base_hyperlink.rstrip('/')}")
            ),
        )


class DomainResourceRecordSetListResponse(
    PaginatedResponse[DomainResourceRecordSetResponse]
):
    kind = "DomainResourceRecordSetList"
