# Copyright 2024-2025 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from unittest.mock import call, Mock

import pytest

from maascommon.enums.dns import DnsUpdateAction
from maascommon.enums.ipaddress import IpAddressType
from maascommon.logging.security import AUTHZ_ADMIN, SECURITY
from maasservicelayer.builders.dnsresources import DNSResourceBuilder
from maasservicelayer.context import Context
from maasservicelayer.db.repositories.dnsresources import DNSResourceRepository
from maasservicelayer.models.base import MaasBaseModel
from maasservicelayer.models.dnsresources import DNSResource
from maasservicelayer.models.domains import Domain
from maasservicelayer.models.fabrics import Fabric
from maasservicelayer.models.staticipaddress import StaticIPAddress
from maasservicelayer.models.subnets import Subnet
from maasservicelayer.models.vlans import Vlan
from maasservicelayer.services import dnsresources as dnsresources_module
from maasservicelayer.services.base import BaseService
from maasservicelayer.services.dnspublications import DNSPublicationsService
from maasservicelayer.services.dnsresources import DNSResourcesService
from maasservicelayer.services.domains import DomainsService
from maasservicelayer.utils.date import utcnow
from tests.fixtures import MockLoggerMixin
from tests.maasservicelayer.services.base import ServiceCommonTests


@pytest.mark.asyncio
class TestCommonDNSResourcesService(ServiceCommonTests, MockLoggerMixin):
    module = dnsresources_module

    @pytest.fixture
    def service_instance(self) -> BaseService:
        return DNSResourcesService(
            Context(),
            domains_service=Mock(DomainsService),
            dnspublications_service=Mock(DNSPublicationsService),
            dnsresource_repository=Mock(DNSResourceRepository),
        )

    @pytest.fixture
    def test_instance(self) -> MaasBaseModel:
        domain = Domain(
            id=0,
            name="test_domain",
            authoritative=True,
            created=utcnow(),
            updated=utcnow(),
        )
        return DNSResource(
            id=1,
            name="example",
            domain_id=domain.id,
            created=utcnow(),
            updated=utcnow(),
        )

    async def test_update_many(
        self, service_instance, test_instance: MaasBaseModel, builder_model
    ):
        with pytest.raises(NotImplementedError):
            await super().test_update_many(
                service_instance, test_instance, builder_model
            )

    async def test_delete_many(
        self, service_instance, test_instance: MaasBaseModel
    ):
        with pytest.raises(NotImplementedError):
            await super().test_delete_many(service_instance, test_instance)

    async def test_post_create_hook(
        self, service_instance, test_instance: MaasBaseModel, mock_logger: Mock
    ):
        await service_instance.post_create_hook(test_instance)
        mock_logger.info.assert_called_with(
            f"{AUTHZ_ADMIN}:dnsresource:created:{test_instance.id}",  # noqa: F821
            type=SECURITY,
        )

    async def test_post_update_hook(
        self, service_instance, test_instance: MaasBaseModel, mock_logger: Mock
    ):
        await service_instance.post_update_hook(test_instance, test_instance)
        mock_logger.info.assert_called_with(
            f"{AUTHZ_ADMIN}:dnsresource:updated:{test_instance.id}",
            type=SECURITY,
        )

    async def test_post_delete_hook(
        self, service_instance, test_instance: MaasBaseModel, mock_logger: Mock
    ):
        await service_instance.post_delete_hook(test_instance)
        mock_logger.info.assert_called_with(
            f"{AUTHZ_ADMIN}:dnsresource:deleted:{test_instance.id}",
            type=SECURITY,
        )


@pytest.mark.asyncio
class TestDNSResourcesService:
    async def test_create(self) -> None:
        mock_domains_service = Mock(DomainsService)
        mock_dnspublications_service = Mock(DNSPublicationsService)
        mock_dnsresource_repository = Mock(DNSResourceRepository)

        domain = Domain(
            id=0,
            name="test_domain",
            authoritative=True,
            created=utcnow(),
            updated=utcnow(),
        )
        dnsresource = DNSResource(
            id=1,
            name="example",
            domain_id=domain.id,
            created=utcnow(),
            updated=utcnow(),
        )

        mock_domains_service.get_one.return_value = domain
        mock_dnsresource_repository.create.return_value = dnsresource

        service = DNSResourcesService(
            Context(),
            domains_service=mock_domains_service,
            dnspublications_service=mock_dnspublications_service,
            dnsresource_repository=mock_dnsresource_repository,
        )

        builder = DNSResourceBuilder(
            name=dnsresource.name,
            domain_id=domain.id,
        )
        await service.create(builder)

        mock_dnsresource_repository.create.assert_called_once_with(
            builder=builder
        )
        mock_dnspublications_service.create_for_config_update.assert_called_once_with(
            source="zone test_domain added resource example",
            action=DnsUpdateAction.INSERT_NAME,
            label="example",
            rtype="A",
            zone="test_domain",
        )

    async def test_update_change_domain(self) -> None:
        mock_domains_service = Mock(DomainsService)
        mock_dnspublications_service = Mock(DNSPublicationsService)
        mock_dnsresource_repository = Mock(DNSResourceRepository)

        old_domain = Domain(
            id=0,
            name="test_domain",
            authoritative=True,
            created=utcnow(),
            updated=utcnow(),
        )
        new_domain = Domain(
            id=1,
            name="new_domain",
            authoritative=True,
            created=utcnow(),
            updated=utcnow(),
        )
        old_dnsresource = DNSResource(
            id=2,
            name="example",
            domain_id=old_domain.id,
            created=utcnow(),
            updated=utcnow(),
        )
        new_dnsresource = DNSResource(
            id=2,
            name="example",
            domain_id=new_domain.id,
            created=utcnow(),
            updated=utcnow(),
        )
        domain_list = [old_domain, new_domain]

        builder = DNSResourceBuilder(
            name=new_dnsresource.name, domain_id=new_domain.id
        )

        mock_domains_service.get_one.side_effect = domain_list
        mock_dnsresource_repository.get_by_id.return_value = old_dnsresource
        mock_dnsresource_repository.update_by_id.return_value = new_dnsresource

        service = DNSResourcesService(
            Context(),
            domains_service=mock_domains_service,
            dnspublications_service=mock_dnspublications_service,
            dnsresource_repository=mock_dnsresource_repository,
        )

        await service.update_by_id(old_dnsresource.id, builder)

        mock_dnsresource_repository.update_by_id.assert_called_once_with(
            id=old_dnsresource.id, builder=builder
        )
        mock_dnspublications_service.create_for_config_update.assert_has_calls(
            [
                call(
                    source="zone test_domain removed resource example",
                    action=DnsUpdateAction.DELETE,
                    label=old_dnsresource.name,
                    rtype="A",
                    zone=old_domain.name,
                ),
                call(
                    source="zone new_domain added resource example",
                    action=DnsUpdateAction.INSERT_NAME,
                    label=new_dnsresource.name,
                    rtype="A",
                    zone=new_domain.name,
                ),
            ],
        )

    async def test_update_change_ttl(self) -> None:
        mock_domains_service = Mock(DomainsService)
        mock_dnspublications_service = Mock(DNSPublicationsService)
        mock_dnsresource_repository = Mock(DNSResourceRepository)

        domain = Domain(
            id=0,
            name="test_domain",
            authoritative=True,
            created=utcnow(),
            updated=utcnow(),
        )
        old_dnsresource = DNSResource(
            id=1,
            name="example",
            domain_id=domain.id,
            created=utcnow(),
            updated=utcnow(),
        )
        dnsresource = DNSResource(
            id=1,
            name="example",
            domain_id=domain.id,
            created=utcnow(),
            updated=utcnow(),
            address_ttl=45,
        )

        builder = DNSResourceBuilder(
            name=dnsresource.name, domain_id=domain.id, address_ttl=45
        )

        mock_domains_service.get_one.return_value = domain
        mock_dnsresource_repository.get_by_id.return_value = old_dnsresource
        mock_dnsresource_repository.update_by_id.return_value = dnsresource

        service = DNSResourcesService(
            Context(),
            domains_service=mock_domains_service,
            dnspublications_service=mock_dnspublications_service,
            dnsresource_repository=mock_dnsresource_repository,
        )

        await service.update_by_id(old_dnsresource.id, builder)

        mock_dnsresource_repository.update_by_id.assert_called_once_with(
            id=old_dnsresource.id, builder=builder
        )
        mock_dnspublications_service.create_for_config_update.assert_called_once_with(
            source="zone test_domain updated resource example",
            action=DnsUpdateAction.UPDATE,
            label=dnsresource.name,
            rtype="A",
            zone=domain.name,
            ttl=45,
        )

    async def test_delete(self) -> None:
        mock_domains_service = Mock(DomainsService)
        mock_dnspublications_service = Mock(DNSPublicationsService)
        mock_dnsresource_repository = Mock(DNSResourceRepository)

        domain = Domain(
            id=0,
            name="test_domain",
            authoritative=True,
            created=utcnow(),
            updated=utcnow(),
        )
        dnsresource = DNSResource(
            id=1,
            name="example",
            domain_id=domain.id,
            created=utcnow(),
            updated=utcnow(),
        )

        mock_domains_service.get_one.return_value = domain
        mock_dnsresource_repository.get_by_id.return_value = dnsresource
        mock_dnsresource_repository.delete_by_id.return_value = dnsresource

        service = DNSResourcesService(
            Context(),
            domains_service=mock_domains_service,
            dnspublications_service=mock_dnspublications_service,
            dnsresource_repository=mock_dnsresource_repository,
        )

        await service.delete_by_id(dnsresource.id)

        mock_dnsresource_repository.delete_by_id.assert_called_once_with(
            id=dnsresource.id
        )
        mock_dnspublications_service.create_for_config_update.assert_called_once_with(
            source="zone test_domain removed resource example",
            action=DnsUpdateAction.DELETE,
            label=dnsresource.name,
            rtype="A",
            zone=domain.name,
        )

    async def test_release_dynamic_hostname_no_remaining_ips(self) -> None:
        mock_domains_service = Mock(DomainsService)
        mock_dnspublications_service = Mock(DNSPublicationsService)
        domain = Domain(
            id=0,
            name="test_domain",
            authoritative=True,
            created=utcnow(),
            updated=utcnow(),
        )
        mock_domains_service.get_default_domain.return_value = domain

        dnsresource = DNSResource(
            id=1,
            name="test_name",
            domain_id=0,
            created=utcnow(),
            updated=utcnow(),
        )

        sip = StaticIPAddress(
            id=1,
            ip="10.0.0.1",
            alloc_type=IpAddressType.DISCOVERED,
            lease_time=600,
            subnet_id=2,
            created=utcnow(),
            updated=utcnow(),
        )

        mock_dnsresource_repository = Mock(DNSResourceRepository)
        mock_dnsresource_repository.get_dnsresources_in_domain_for_ip.return_value = [
            dnsresource
        ]
        mock_dnsresource_repository.get_ips_for_dnsresource.side_effect = [
            [sip],
            [],
        ]

        dnsresources_service = DNSResourcesService(
            context=Context(),
            domains_service=mock_domains_service,
            dnspublications_service=mock_dnspublications_service,
            dnsresource_repository=mock_dnsresource_repository,
        )

        await dnsresources_service.release_dynamic_hostname(sip)

        mock_dnsresource_repository.get_dnsresources_in_domain_for_ip.assert_called_once_with(
            domain, sip
        )

        assert (
            mock_dnsresource_repository.get_ips_for_dnsresource.call_args_list[
                0
            ]
            == call(
                dnsrr_id=dnsresource.id, discovered_only=True, matching=sip
            )
        )
        assert (
            mock_dnsresource_repository.get_ips_for_dnsresource.call_args_list[
                1
            ]
            == call(
                dnsrr_id=dnsresource.id, discovered_only=False, matching=None
            )
        )

        mock_dnsresource_repository.remove_ip_relation.assert_called_once_with(
            dnsresource, sip
        )
        mock_dnspublications_service.create_for_config_update.assert_called_once_with(
            source="zone test_domain removed resource test_name",
            action=DnsUpdateAction.DELETE,
            label=dnsresource.name,
            rtype="A",
            zone="test_domain",
        )

    async def test_update_dynamic_hostname(self) -> None:
        mock_domains_service = Mock(DomainsService)
        mock_dnspublications_service = Mock(DNSPublicationsService)
        domain = Domain(
            id=0,
            name="test_domain",
            authoritative=True,
            created=utcnow(),
            updated=utcnow(),
        )
        mock_domains_service.get_default_domain.return_value = domain

        sip = StaticIPAddress(
            id=1,
            ip="10.0.0.1",
            alloc_type=IpAddressType.DISCOVERED,
            lease_time=600,
            subnet_id=2,
            created=utcnow(),
            updated=utcnow(),
        )
        dnsresource = DNSResource(
            id=1,
            name="test_name",
            domain_id=0,
            created=utcnow(),
            updated=utcnow(),
        )

        mock_dnsresource_repository = Mock(DNSResourceRepository)
        mock_dnsresource_repository.get_one.return_value = dnsresource
        mock_dnsresource_repository.get_dnsresources_in_domain_for_ip.side_effect = [
            [],
            [dnsresource],
        ]
        mock_dnsresource_repository.get_ips_for_dnsresource.return_value = []

        dnsresources_service = DNSResourcesService(
            context=Context(),
            domains_service=mock_domains_service,
            dnspublications_service=mock_dnspublications_service,
            dnsresource_repository=mock_dnsresource_repository,
        )

        await dnsresources_service.update_dynamic_hostname(sip, "test_name")
        assert (
            mock_dnsresource_repository.get_ips_for_dnsresource.call_args_list[
                0
            ]
            == call(
                dnsrr_id=dnsresource.id, discovered_only=False, matching=None
            )
        )
        assert (
            mock_dnsresource_repository.get_ips_for_dnsresource.call_args_list[
                1
            ]
            == call(
                dnsrr_id=dnsresource.id, discovered_only=True, matching=None
            )
        )
        mock_dnsresource_repository.link_ip.assert_called_once_with(
            dnsresource.id, sip.id
        )
        mock_dnspublications_service.create_for_config_update.assert_called_once_with(
            source="ip 10.0.0.1 linked to resource test_name on zone test_domain",
            action=DnsUpdateAction.INSERT,
            label=dnsresource.name,
            rtype="A",
            ttl=30,
            zone=domain.name,
            answer="10.0.0.1",
        )

    async def test_add_ip(self):
        mock_domains_service = Mock(DomainsService)
        mock_dnspublications_service = Mock(DNSPublicationsService)
        mock_dnsresource_repository = Mock(DNSResourceRepository)
        dnsresources_service = DNSResourcesService(
            context=Context(),
            domains_service=mock_domains_service,
            dnspublications_service=mock_dnspublications_service,
            dnsresource_repository=mock_dnsresource_repository,
        )

        fabric = Fabric(id=7)
        vlan = Vlan(
            id=6,
            vid=0,
            description="",
            mtu=1500,
            dhcp_on=True,
            fabric_id=fabric.id,
        )
        subnet = Subnet(
            id=5,
            cidr="10.0.0.0/24",
            allow_dns=True,
            allow_proxy=True,
            active_discovery=True,
            rdns_mode=1,
            managed=True,
            disabled_boot_architectures=[],
            vlan_id=vlan.id,
        )
        sip = StaticIPAddress(
            id=1,
            alloc_type=IpAddressType.AUTO,
            lease_time=30,
            subnet_id=subnet.id,
            ip="10.0.0.1",
        )
        domain = Domain(
            id=2,
            name="test-domain",
            authoritative=True,
            ttl=30,
        )
        dnsrr = DNSResource(
            id=3,
            name="test-name",
            domain_id=domain.id,
        )

        mock_dnsresource_repository.get_one.return_value = dnsrr

        await dnsresources_service.add_ip(sip, dnsrr.name, domain)

        mock_dnsresource_repository.link_ip.assert_called_once_with(
            dnsrr.id, sip.id
        )

    async def test_remove_ip(self):
        mock_domains_service = Mock(DomainsService)
        mock_dnspublications_service = Mock(DNSPublicationsService)
        mock_dnsresource_repository = Mock(DNSResourceRepository)
        dnsresources_service = DNSResourcesService(
            context=Context(),
            domains_service=mock_domains_service,
            dnspublications_service=mock_dnspublications_service,
            dnsresource_repository=mock_dnsresource_repository,
        )

        fabric = Fabric(id=7)
        vlan = Vlan(
            id=6,
            vid=0,
            description="",
            mtu=1500,
            dhcp_on=True,
            fabric_id=fabric.id,
        )
        subnet = Subnet(
            id=5,
            cidr="10.0.0.0/24",
            allow_dns=True,
            allow_proxy=True,
            active_discovery=True,
            rdns_mode=1,
            managed=True,
            disabled_boot_architectures=[],
            vlan_id=vlan.id,
        )
        sip = StaticIPAddress(
            id=1,
            alloc_type=IpAddressType.AUTO,
            lease_time=30,
            subnet_id=subnet.id,
            ip="10.0.0.1",
        )
        domain = Domain(
            id=2,
            name="test-domain",
            authoritative=True,
            ttl=30,
        )
        dnsrr = DNSResource(
            id=3,
            name="test-name",
            domain_id=domain.id,
        )

        mock_dnsresource_repository.get_one.return_value = dnsrr

        await dnsresources_service.remove_ip(sip, dnsrr.name, domain)

        mock_dnsresource_repository.remove_ip_relation.assert_called_once_with(
            dnsrr, sip
        )
