# Copyright 2025 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from unittest.mock import Mock

from fastapi import Response
import pytest
from starlette.types import ASGIApp

from maasapiserver.v3.middlewares.client_certificate import (
    RequireClientCertMiddleware,
)


@pytest.fixture
def middleware():
    return RequireClientCertMiddleware(
        Mock(ASGIApp), header_name="client-cert-cn"
    )


class TestRequireClientCertMiddleware:
    async def test_missing_client_cert_returns_403(self, middleware):
        mock_request = type(
            "Request",
            (),
            {
                "scope": {
                    "headers": [],
                    "path": "/path/to/endpoint",
                    "method": "GET",
                }
            },
        )
        mock_request_instance = mock_request()

        async def mock_call_next(request):
            return Response("OK")

        response = await middleware.dispatch(
            mock_request_instance, mock_call_next
        )

        assert response.status_code == 403
        assert response.body == b'{"detail":"Client certificate required."}'

    async def test_valid_client_cert_continues_chain(self, middleware):
        mock_request = type(
            "Request",
            (),
            {
                "scope": {
                    "headers": [(b"client-cert-cn", b"test-client-cert")],
                    "path": "/path/to/endpoint",
                    "method": "GET",
                }
            },
        )
        mock_request_instance = mock_request()

        async def mock_call_next(request):
            return Response("OK")

        response = await middleware.dispatch(
            mock_request_instance, mock_call_next
        )
        assert response.body == b"OK"

    async def test_agent_enroll_endpoint_skips_cert_check(self, middleware):
        mock_request = type(
            "Request",
            (),
            {
                "scope": {
                    "headers": [],
                    "path": "/v3/agents:enroll",
                    "method": "POST",
                }
            },
        )
        mock_request_instance = mock_request()

        async def mock_call_next(request):
            return Response("OK")

        response = await middleware.dispatch(
            mock_request_instance, mock_call_next
        )
        assert response.body == b"OK"
