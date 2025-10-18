#  Copyright 2024 Canonical Ltd.  This software is licensed under the
#  GNU Affero General Public License version 3 (see the file LICENSE).

from datetime import datetime

from fastapi import Depends, Response
from OpenSSL import crypto

from maasapiserver.common.api.base import Handler, handler
from maasapiserver.common.api.models.responses.errors import (
    UnauthorizedBodyResponse,
)
from maasapiserver.v3.api import services
from maasapiserver.v3.api.internal.models.requests.agent import AgentRequest
from maasapiserver.v3.api.internal.models.responses.agent import (
    AgentResponse,
    AgentSignedCertificateResponse,
)
from maasapiserver.v3.api.public.models.responses.base import (
    OPENAPI_ETAG_HEADER,
)
from maasapiserver.v3.constants import V3_INTERNAL_API_PREFIX
from maasservicelayer.builders.agents import AgentBuilder
from maasservicelayer.db.filters import QuerySpec
from maasservicelayer.db.repositories.bootstraptokens import (
    BootstrapTokensClauseFactory,
)
from maasservicelayer.db.repositories.racks import RacksClauseFactory
from maasservicelayer.exceptions.catalog import (
    BadRequestException,
    BaseExceptionDetail,
    UnauthorizedException,
)
from maasservicelayer.exceptions.constants import (
    INVALID_ARGUMENT_VIOLATION_TYPE,
    INVALID_TOKEN_VIOLATION_TYPE,
    UNEXISTING_RESOURCE_VIOLATION_TYPE,
)
from maasservicelayer.models.secrets import MAASCACertificateSecret
from maasservicelayer.services import ServiceCollectionV3
from maasservicelayer.utils.date import utcnow
from provisioningserver.certificates import Certificate, CertificateRequest


async def fetch_maas_ca_cert(services: ServiceCollectionV3) -> Certificate:
    secret_maas_ca = await services.secrets.get_composite_secret(
        MAASCACertificateSecret(), default=None
    )
    ca_cert = Certificate.from_pem(
        secret_maas_ca["key"],
        secret_maas_ca["cert"],
        ca_certs_material=secret_maas_ca.get("cacert", ""),
    )
    return ca_cert


async def sign_certificate_request(
    ca_cert: Certificate, csr_pem: str
) -> tuple[bytes, str, datetime]:
    """
    Signs a PEM-encoded Certificate Signing Request (CSR) using a CA
    certificate.

    Inputs
    - ca_cert: the certificate of the Certificate Authority (CA) used to sign
      the CSR.
    - csr_pem (str): PEM-encoded certificate signing request to be signed.

    Outputs
    - signed certificate in PEM format (bytes).
    - SHA-256 fingerprint of the signed certificate (hex string, no colons,
      lower case).
    - expiration date (`notAfter`) of the signed certificate as a `datetime`.
    """
    csr = crypto.load_certificate_request(
        crypto.FILETYPE_PEM, csr_pem.encode()
    )
    request = CertificateRequest(key=csr.get_pubkey(), csr=csr)

    signed_cert = ca_cert.sign_certificate_request(request)

    cert_pem = crypto.dump_certificate(crypto.FILETYPE_PEM, signed_cert.cert)
    fingerprint = (
        signed_cert.cert.digest("sha256")
        .decode("utf-8")
        .replace(":", "")
        .lower()
    )

    not_after_bytes = signed_cert.cert.get_notAfter()
    if not_after_bytes is None:
        raise BadRequestException(
            details=[
                BaseExceptionDetail(
                    type=INVALID_ARGUMENT_VIOLATION_TYPE,
                    message="Signed certificate is missing the 'notAfter' field.",
                ),
            ],
        )
    not_after = datetime.strptime(
        not_after_bytes.decode("ascii"), "%Y%m%d%H%M%SZ"
    )

    return cert_pem, fingerprint, not_after


class AgentHandler(Handler):
    """
    MAAS Agent API handler provides collection of handlers that can be called
    by the Agent to fetch configuration for its various services or push back
    data that should be known to MAAS Region Controller
    """

    @handler(
        path="/agents/{system_id}/services/{service_name}/config",
        methods=["GET"],
        responses={
            201: {
                "model": AgentResponse,
                "headers": {"ETag": OPENAPI_ETAG_HEADER},
            },
        },
    )
    async def get_agent_service_config(
        self,
        system_id: str,
        service_name: str,
        response: Response,
        services: ServiceCollectionV3 = Depends(services),  # noqa: B008
    ) -> Response:
        tokens = await services.agents.get_service_configuration(
            system_id, service_name
        )
        return tokens

    @handler(
        path="/agents:enroll",
        methods=["POST"],
        responses={
            201: {
                "model": AgentSignedCertificateResponse,
                "headers": {"ETag": OPENAPI_ETAG_HEADER},
            },
            401: {"model": UnauthorizedBodyResponse},
        },
        status_code=201,
    )
    async def enroll_agent(
        self,
        agent_request: AgentRequest,
        response: Response,
        services: ServiceCollectionV3 = Depends(services),  # noqa: B008
    ) -> AgentSignedCertificateResponse:
        # @TODO
        # - deal with legacy rack controller
        #   - rackcontroller_id is nullable during the WIP phase
        #   - investigate enrollment
        #     Once that we build the development of MAE, we need to investigate
        #     how to create a rack controller and creat it

        # @TODO:
        # - investigate
        #    - if the token has been used, what happens if the user tries to use it again?

        # fulfill CSR
        # """
        # CSR components (https://cryptography.io/en/latest/x509/tutorial/):
        # - Information about our public key (including a signature of the entire body).
        # - Information about who we are -> agent ID
        # - Information about what domains this certificate is for.
        # """

        # @TODO
        # - guarantee atomic transaction to avoid signing 2 certificates simultaneously when the token is used
        # - save certificate in the AgentCertificate table with an expiration date and fingerprint
        # - add events

        bootstraptoken = await services.bootstraptokens.get_one(
            query=QuerySpec(
                where=BootstrapTokensClauseFactory.with_secret(
                    agent_request.secret
                )
            )
        )
        if bootstraptoken is None or utcnow() >= bootstraptoken.expires_at:
            raise UnauthorizedException(
                details=[
                    BaseExceptionDetail(
                        type=INVALID_TOKEN_VIOLATION_TYPE,
                        message="Enrollment secret invalid or expired.",
                    )
                ]
            )

        rack = await services.racks.get_one(
            query=QuerySpec(
                where=RacksClauseFactory.with_rack_id(bootstraptoken.rack_id)
            )
        )
        if rack is None:
            raise UnauthorizedException(
                details=[
                    BaseExceptionDetail(
                        type=UNEXISTING_RESOURCE_VIOLATION_TYPE,
                        message="The enrollment secret is invalid or no longer associated with a valid resource.",
                    )
                ]
            )

        # load CSR and sign certificate
        ca_cert = await fetch_maas_ca_cert(services)
        (
            cert_pem_bytes,
            fingerprint,
            revoked_at,
        ) = await sign_certificate_request(ca_cert, agent_request.csr)

        # create Agent
        a_builder = AgentBuilder(rack_id=rack.id)
        agent = await services.agents.create(a_builder)

        response.headers["ETag"] = agent.etag()
        return AgentSignedCertificateResponse.from_model(
            certificate=cert_pem_bytes.decode("utf-8"),
            self_base_hyperlink=f"{V3_INTERNAL_API_PREFIX}/agents:enroll",
        )
