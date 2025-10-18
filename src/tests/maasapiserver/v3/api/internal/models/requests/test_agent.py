#  Copyright 2024-2025 Canonical Ltd.  This software is licensed under the
#  GNU Affero General Public License version 3 (see the file LICENSE).

import pytest

from maasapiserver.v3.api.internal.models.requests.agent import AgentRequest
from maasservicelayer.exceptions.catalog import ValidationException

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


class TestAgentRequest:
    def test_validate_valid_csr(self) -> None:
        agent_request = AgentRequest(
            secret="secret",
            csr=CSR,
        )
        assert agent_request.secret == "secret"
        assert agent_request.csr == CSR

    def test_validate_invalid_csr(self) -> None:
        with pytest.raises(ValidationException) as e:
            AgentRequest(
                secret="secret",
                csr="invalid-csr",
            )
        assert "Invalid PEM certificate." == e.value.details[0].message
