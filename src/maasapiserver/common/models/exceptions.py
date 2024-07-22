from pydantic import BaseModel

from maasapiserver.common.api.models.responses.errors import (
    DischargeRequiredErrorBodyResponse,
)


class BaseExceptionDetail(BaseModel):
    type: str
    message: str


class BaseException(Exception):
    def __init__(
        self, message: str, details: list[BaseExceptionDetail] | None = None
    ):
        super().__init__(message)
        self.details = details


class AlreadyExistsException(BaseException):
    def __init__(self, details: list[BaseExceptionDetail] | None = None):
        super().__init__(
            "An instance with the same unique attributes already exists.",
            details,
        )


class BadRequestException(BaseException):
    def __init__(self, details: list[BaseExceptionDetail] | None = None):
        super().__init__(
            "Invalid request. Please check the provided data.", details
        )


class NotFoundException(BaseException):
    def __init__(self, details: list[BaseExceptionDetail] | None = None):
        super().__init__("The requested resource was not found.", details)


class UnauthorizedException(BaseException):
    def __init__(self, details: list[BaseExceptionDetail] | None = None):
        super().__init__("Not authenticated.", details)


class ForbiddenException(BaseException):
    def __init__(self, details: list[BaseExceptionDetail] | None = None):
        super().__init__("Forbidden.", details)


class PreconditionFailedException(BaseException):
    def __init__(self, details: list[BaseExceptionDetail] | None = None):
        super().__init__("A precondition has failed.", details)


class ServiceUnavailableException(BaseException):
    def __init__(self, details: list[BaseExceptionDetail] | None = None):
        super().__init__("The service is not available.", details)


class DischargeRequiredException(Exception):
    def __init__(self, body: DischargeRequiredErrorBodyResponse):
        super().__init__("Macaroon discharge required.")
        self.body = body
