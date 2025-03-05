#  Copyright 2024-2025 Canonical Ltd.  This software is licensed under the
#  GNU Affero General Public License version 3 (see the file LICENSE).

from ipaddress import IPv4Address
from unittest.mock import Mock

import pytest

from maascommon.dns import DomainDnsRecord
from maasservicelayer.models.dnsresourcerecordsets import (
    ADnsRecord,
    DnsResourceRecordSet,
    DnsResourceTypeEnum,
    TxtDnsRecord,
)
from maasservicelayer.services.dnsresourcerecordsets import (
    V3DnsResourceRecordSetsService,
)
from maasservicelayer.services.domains import DomainsService


@pytest.mark.asyncio
class TestV3DnsResourceRecordSetsService:
    async def test_get_rrsets_for_domain(self) -> None:
        domains_service = Mock(DomainsService)
        v3dnsrrsets_service = V3DnsResourceRecordSetsService(
            domains_service=domains_service
        )
        domains_service.v3_render_json_for_related_rrdata.return_value = {
            "example.com": [
                DomainDnsRecord(
                    name="example.com",
                    system_id="abcdef",
                    node_type=None,
                    user_id=None,
                    dnsresource_id=None,
                    node_id=1,
                    ttl=30,
                    rrtype=DnsResourceTypeEnum.A,
                    rrdata="10.0.0.2",
                    dnsdata_id=None,
                ),
                DomainDnsRecord(
                    name="example.com",
                    system_id="abcdef",
                    node_type=None,
                    user_id=None,
                    dnsresource_id=None,
                    node_id=1,
                    ttl=30,
                    rrtype=DnsResourceTypeEnum.A,
                    rrdata="10.0.0.3",
                    dnsdata_id=None,
                ),
                DomainDnsRecord(
                    name="example.com",
                    system_id="abcdef",
                    node_type=None,
                    user_id=None,
                    dnsresource_id=None,
                    node_id=None,
                    ttl=30,
                    rrtype=DnsResourceTypeEnum.TXT,
                    rrdata="Some random text data.",
                    dnsdata_id=None,
                ),
            ]
        }

        rrsets_for_domains = await v3dnsrrsets_service.get_rrsets_for_domain(1)
        assert rrsets_for_domains == [
            DnsResourceRecordSet(
                name="example.com",
                node_id=1,
                ttl=30,
                rrtype=DnsResourceTypeEnum.A,
                a_records=[
                    ADnsRecord(address=IPv4Address("10.0.0.2")),
                    ADnsRecord(address=IPv4Address("10.0.0.3")),
                ],
            ),
            DnsResourceRecordSet(
                name="example.com",
                ttl=30,
                rrtype=DnsResourceTypeEnum.TXT,
                txt_records=[TxtDnsRecord(txt_data="Some random text data.")],
            ),
        ]
