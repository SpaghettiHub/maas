#  Copyright 2024-2025 Canonical Ltd.  This software is licensed under the
#  GNU Affero General Public License version 3 (see the file LICENSE).

"""
Middleware for extracting client certificate information from TLS connections.
"""

from typing import Awaitable, Callable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp
import structlog

logger = structlog.getLogger(__name__)


class RequireClientCertMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, header_name: str):
        super().__init__(app)
        self.header_name = header_name.encode()

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ):
        headers = dict(request.scope.get("headers", []))

        # skip client cert check for agent enrollment endpoint
        if (
            request.scope["path"].endswith("/agents:enroll")
            and request.scope["method"] == "POST"
        ):
            return await call_next(request)

        header_content = headers.get(self.header_name)
        if not header_content:
            return JSONResponse(
                {"detail": "Client certificate required."},
                status_code=403,
            )

        return await call_next(request)
