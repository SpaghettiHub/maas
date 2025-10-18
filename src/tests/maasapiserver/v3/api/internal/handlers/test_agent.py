# Copyright 2025 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, patch

from httpx import AsyncClient
import pytest

from maasapiserver.v3.constants import V3_INTERNAL_API_PREFIX
from maasservicelayer.exceptions.constants import INVALID_TOKEN_VIOLATION_TYPE
from maasservicelayer.models.agents import Agent
from maasservicelayer.models.bootstraptokens import BootstrapToken
from maasservicelayer.models.racks import Rack
from maasservicelayer.services import ServiceCollectionV3
from maasservicelayer.services.agents import AgentsService
from maasservicelayer.services.bootstraptoken import BootstrapTokensService
from maasservicelayer.services.racks import RacksService
from maasservicelayer.services.secrets import SecretsService
from maasservicelayer.utils.date import utcnow

CSR = "\n".join(
    [
        "-----BEGIN CERTIFICATE REQUEST-----",
        "MIIEdDCCAlwCAQAwLzEtMCsGA1UEAxMkMDFmMDlkMzItZjUwOC02MDY0LWJkMWMt",
        "YzAyNWE1OGRkMDY4MIICIjANBgkqhkiG9w0BAQEFAAOCAg8AMIICCgKCAgEA0ax1",
        "JULvRXrCEu7cJSGtzTfGxUAD6T9aC3EWifoOlHETP9OFuPihDxVYqrgoOS83mWJ6",
        "FN5koXLGheEGs0t665lWGi28q21CRCTiCY9U0nTVq5D0uZLOMj83NTuE1W3mLL4i",
        "FwWwKf66lOPRhN/FY3C9C8Yd+eTWAf2RIHqvQbNMOKaGogIOLG5rYF9owVJdTpd+",
        "tT5Oy3CSHKHYMa5c8wuIBfxdtcBJBuo1++cjZGfwzv0Kl1sU/6/QUsdJcZnRZvqm",
        "0CpCwBJvPWYuxIxfkUHbiuLTHj2oLEwvULATzZePEiSpyRXasWuKSAK9WX8UM24M",
        "yT0pFykil/p7xSClpuuN8mQ65Ji0qSrQ2olfmgdjs7EFtUcAyPo8SKQHO5aQ1C9L",
        "SF/zJcVaQThaQzqHRjQnSmNcv5p6xmcMwwuLQEwpBdlALvDKgRH/EDI0+Qgn5AF5",
        "NYeMsqXo8aghOpSMt8HIqoKe3tTHJM8HWNjO32FODBVHsWGo9O1vInfBO/3NPrPn",
        "4oXitL0DrXfn0dWIh2Oy4GmyJhzmfFHIfpY/91C7vGlyRYzpIPTxash1pLS7Nu0g",
        "qBk3uWk92KeYVISodisf3TVlgDbNs07QCVGD7fjgMeIy/vT8yfbWP4KYWbXyqBsB",
        "mpQOVNFRdnfuOWbGtcHS9kK6HJdPduhMPvsV+3sCAwEAAaAAMA0GCSqGSIb3DQEB",
        "CwUAA4ICAQAiR+eN3xI5CosLqvSnlhOcO9Ucfp3gFERFLtcsCJGP1hB6E7MIwiGj",
        "JJbaYjpOWV8+Llf+SkqhSpJxlp0L3xvSvWBkUvd7Q0rYCtitwlXvOz5aGAT9neDj",
        "LwcKkgoByICsHncq1V23Izq060FbQqZVwniQAjFLEwHT7JCxPnMUxxtlQjRYA7Sb",
        "wACvpVwmiw+fgUUw0zVNC/9wjmpUO9xLPDeLqdAw0BMWxgDTvEE92mw9G62XS/mi",
        "MeaEpNdKgsWsVw1mHxCvwCXeb3HOmnsKTtMDgjmexw44pTsrKwNUo5guX0s8/LQf",
        "r9GgQB4Fez6avFZ4Ha8xzlxolOfGGkCF8dcFPaMunVwjUI1/IYy+R7Ty/+9vRab7",
        "Pds/dhjt2EMs8CznpPRFlZQOOhXtkX5JCkK8yyx9PyivHOaZC2ea6XX2c6swnOU9",
        "6LVfM+RIGoeCXxXsacAGQEahOhMvFZ8UdcTU2plRzKe4xvipxkIg3XZbIk82FCwe",
        "ImpfiaqzHorVHOnBEYmC6KWSDF1DL192s2U6FB5rWE3Uw4ErnLjfuhJyU7bIAv40",
        "DrQ9wTpaby5CwBc84T2X+QKPxkmM2toNTg904fHzwuRkAAECeyaD0sdyGOxMFw1W",
        "WxQQmcelrKKSEP23RcF+Kkz7REmIcWKdm97Hk3nmdR6YnM2UHzXBYQ==",
        "-----END CERTIFICATE REQUEST-----",
    ]
)


class TestAgentsApi:
    BASE_PATH = f"{V3_INTERNAL_API_PREFIX}/agents"

    @pytest.fixture
    def internal_api_headers(self) -> dict:
        """Returns headers required for internal API requests"""
        return {"client-cert-cn": "test-client"}

    @patch(
        "maasapiserver.v3.api.internal.handlers.agent.sign_certificate_request",
        new_callable=AsyncMock,
    )
    @patch(
        "maasapiserver.v3.api.internal.handlers.agent.fetch_maas_ca_cert",
        new_callable=AsyncMock,
    )
    async def test_agent_enrollment_success(
        self,
        mock_fetch_maas_ca_cert,
        mock_sign,
        services_mock: ServiceCollectionV3,
        mocked_internal_api_client: AsyncClient,
        internal_api_headers: dict,
    ) -> None:
        fingerprint = b"a1:b2:c3:d4:e5"
        revoked_at = datetime.now(timezone.utc)
        mock_sign.return_value = (
            b"cert_pem_bytes",
            fingerprint,
            revoked_at,
        )
        services_mock.bootstraptokens = Mock(BootstrapTokensService)
        mock_token = BootstrapToken(
            id=1,
            secret="test-secret",
            rack_id=1,
            expires_at=utcnow() + timedelta(minutes=5),
        )
        services_mock.bootstraptokens.get_one.return_value = mock_token
        services_mock.racks = Mock(RacksService)
        mock_rack = Rack(id=1, name="test-rack")
        services_mock.racks.get_one.return_value = mock_rack
        services_mock.secrets = Mock(SecretsService)
        mock_ca_secret = {
            "key": "mock-key",
            "cert": "mock-cert",
            "cacert": "mock-cacert",
        }
        services_mock.secrets.get_composite_secret.return_value = (
            mock_ca_secret
        )
        services_mock.agents = Mock(AgentsService)
        mock_agent = Agent(id=1, rack_id=1)
        services_mock.agents.create.return_value = mock_agent

        request_data = {"secret": "test-secret", "csr": CSR}

        headers = {"client-cert-cn": "test-client"}
        response = await mocked_internal_api_client.post(
            f"{self.BASE_PATH}:enroll",
            json=request_data,
            headers=headers,
        )
        assert response.status_code == 201
        assert "certificate" in response.json()
        assert "ETag" in response.headers

    async def test_agent_enrollment_failed_with_not_found_secret(
        self,
        services_mock: ServiceCollectionV3,
        mocked_internal_api_client: AsyncClient,
        internal_api_headers: dict,
    ) -> None:
        services_mock.bootstraptokens = Mock(BootstrapTokensService)
        services_mock.bootstraptokens.get_one.return_value = None

        request_data = {"secret": "invalid-secret", "csr": CSR}

        response = await mocked_internal_api_client.post(
            f"{self.BASE_PATH}:enroll",
            json=request_data,
            headers=internal_api_headers,
        )
        assert response.status_code == 401
        response_json = response.json()
        assert (
            response_json["details"][0]["type"] == INVALID_TOKEN_VIOLATION_TYPE
        )
        assert (
            response_json["details"][0]["message"]
            == "Enrollment secret invalid or expired."
        )

    async def test_agent_enrollment_with_expired_secret(
        self,
        services_mock: ServiceCollectionV3,
        mocked_internal_api_client: AsyncClient,
        internal_api_headers: dict,
    ) -> None:
        services_mock.bootstraptokens = Mock(BootstrapTokensService)
        mock_token = BootstrapToken(
            id=1,
            secret="test-secret",
            rack_id=1,
            expires_at=utcnow()
            - timedelta(minutes=5),  # expired 5 minutes ago
        )
        services_mock.bootstraptokens.get_one.return_value = mock_token

        request_data = {"secret": "test-secret", "csr": CSR}

        response = await mocked_internal_api_client.post(
            f"{self.BASE_PATH}:enroll",
            json=request_data,
            headers=internal_api_headers,
        )
        assert response.status_code == 401
        response_json = response.json()
        assert (
            response_json["details"][0]["type"] == INVALID_TOKEN_VIOLATION_TYPE
        )
        assert (
            response_json["details"][0]["message"]
            == "Enrollment secret invalid or expired."
        )
