# Copyright 2025 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from ipaddress import IPv4Address, IPv6Address

import pytest

from maasapiserver.v3.api.public.models.responses.domains import (
    AaaaDnsRecordResponse,
    ADnsRecordResponse,
    CnameDnsRecordResponse,
    DomainResourceRecordSetResponse,
    DomainResponse,
    MxDnsRecordResponse,
    NsDnsRecordResponse,
    SrvDnsRecordResponse,
    SshfpDnsRecordResponse,
    TxtDnsRecordResponse,
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


class TestDomainResponse:
    def test_from_model(self) -> None:
        domain = Domain(id=0, name="maas", authoritative=True, ttl=30)
        domain_response = DomainResponse.from_model(
            domain, self_base_hyperlink="http://test"
        )
        assert domain_response.kind == "Domain"
        assert domain_response.id == domain.id
        assert domain_response.name == domain.name
        assert domain_response.authoritative == domain.authoritative
        assert domain_response.ttl == domain.ttl
        assert (
            domain_response.hal_links.self.href == f"http://test/{domain.id}"
        )


class TestADnsRecordResponse:
    def test_from_model(self) -> None:
        record = ADnsRecord(address=IPv4Address("10.0.0.2"))
        record_response = ADnsRecordResponse.from_model(record)
        assert record_response.kind == "ARecord"
        assert record_response.ipv4address == record.address


class TestAaaaDnsRecordResponse:
    def test_from_model(self) -> None:
        record = AaaaDnsRecord(address=IPv6Address("2001:db8::"))
        record_response = AaaaDnsRecordResponse.from_model(record)
        assert record_response.kind == "AaaaRecord"
        assert record_response.ipv6address == record.address


class TestCnameDnsRecordResponse:
    def test_from_model(self) -> None:
        record = CnameDnsRecord(cname="example")
        record_response = CnameDnsRecordResponse.from_model(record)
        assert record_response.kind == "CnameRecord"
        assert record_response.cname == record.cname


class TestMxDnsRecordResponse:
    def test_from_model(self) -> None:
        record = MxDnsRecord(exchange="mailhost.example.com", preference=1)
        record_response = MxDnsRecordResponse.from_model(record)
        assert record_response.kind == "MxRecord"
        assert record_response.exchange == record.exchange
        assert record_response.preference == record.preference


class TestNsDnsRecordResponse:
    def test_from_model(self) -> None:
        record = NsDnsRecord(nsdname="example.com")
        record_response = NsDnsRecordResponse.from_model(record)
        assert record_response.kind == "NsRecord"
        assert record_response.nsdname == record.nsdname


class TestSshfpDnsRecordResponse:
    def test_from_model(self) -> None:
        record = SshfpDnsRecord(
            algorithm=0, fingerprint_type=0, fingerprint="test"
        )
        record_response = SshfpDnsRecordResponse.from_model(record)
        assert record_response.kind == "SshfpRecord"
        assert record_response.algorithm == record.algorithm
        assert record_response.fingerprint_type == record.fingerprint_type
        assert record_response.fingerprint == record.fingerprint


class TestSrvDnsRecordResponse:
    def test_from_model(self) -> None:
        record = SrvDnsRecord(
            port=9000, priority=1, target="server.example.com", weight=5
        )
        record_response = SrvDnsRecordResponse.from_model(record)
        assert record_response.kind == "SrvRecord"
        assert record_response.port == record.port
        assert record_response.priority == record.priority
        assert record_response.target == record.target
        assert record_response.weight == record.weight


class TestTxtDnsRecordResponse:
    def test_from_model(self) -> None:
        record = TxtDnsRecord(txt_data="test")
        record_response = TxtDnsRecordResponse.from_model(record)
        assert record_response.kind == "TxtRecord"
        assert record_response.data == record.txt_data


class TestDomainResourceRecordSetResponse:
    @pytest.mark.parametrize(
        "rrset",
        [
            DnsResourceRecordSet(
                name="example.com",
                rrtype=DnsResourceTypeEnum.A,
                a_records=[ADnsRecord(address=IPv4Address("10.0.0.2"))],
            ),
            DnsResourceRecordSet(
                name="example.com",
                rrtype=DnsResourceTypeEnum.AAAA,
                aaaa_records=[
                    AaaaDnsRecord(address=IPv6Address("2001:db8::"))
                ],
            ),
            DnsResourceRecordSet(
                name="example.com",
                rrtype=DnsResourceTypeEnum.CNAME,
                cname_records=[CnameDnsRecord(cname="example")],
            ),
            DnsResourceRecordSet(
                name="example.com",
                rrtype=DnsResourceTypeEnum.MX,
                mx_records=[
                    MxDnsRecord(exchange="mailhost.example.com", preference=1)
                ],
            ),
            DnsResourceRecordSet(
                name="example.com",
                rrtype=DnsResourceTypeEnum.NS,
                ns_records=[NsDnsRecord(nsdname="example.com")],
            ),
            DnsResourceRecordSet(
                name="example.com",
                rrtype=DnsResourceTypeEnum.SSHFP,
                sshfp_records=[
                    SshfpDnsRecord(
                        algorithm=0, fingerprint_type=0, fingerprint="test"
                    )
                ],
            ),
            DnsResourceRecordSet(
                name="_xmpp._tcp.example.com",
                rrtype=DnsResourceTypeEnum.SRV,
                srv_records=[
                    SrvDnsRecord(
                        port=9000,
                        priority=1,
                        target="server.example.com",
                        weight=5,
                    )
                ],
            ),
            DnsResourceRecordSet(
                name="example.com",
                rrtype=DnsResourceTypeEnum.TXT,
                txt_records=[TxtDnsRecord(txt_data="test")],
            ),
        ],
    )
    def test_from_model(self, rrset: DnsResourceRecordSet) -> None:
        response = DomainResourceRecordSetResponse.from_model(
            rrset, self_base_hyperlink="http://test"
        )
        assert response.kind == "DomainResourceRecordSet"
        assert response.name == rrset.name
        assert response.node_id == rrset.node_id
        assert response.ttl == rrset.ttl
        assert response.rrtype == rrset.rrtype
        match rrset.rrtype:
            case DnsResourceTypeEnum.A:
                assert response.a_records is not None
                assert len(response.a_records) == 1
            case DnsResourceTypeEnum.AAAA:
                assert response.aaaa_records is not None
                assert len(response.aaaa_records) == 1
            case DnsResourceTypeEnum.CNAME:
                assert response.cname_records is not None
                assert len(response.cname_records) == 1
            case DnsResourceTypeEnum.MX:
                assert response.mx_records is not None
                assert len(response.mx_records) == 1
            case DnsResourceTypeEnum.NS:
                assert response.ns_records is not None
                assert len(response.ns_records) == 1
            case DnsResourceTypeEnum.SSHFP:
                assert response.sshfp_records is not None
                assert len(response.sshfp_records) == 1
            case DnsResourceTypeEnum.SRV:
                assert response.srv_records is not None
                assert len(response.srv_records) == 1
            case DnsResourceTypeEnum.TXT:
                assert response.txt_records is not None
                assert len(response.txt_records) == 1

        assert response.hal_links.self.href == "http://test"
