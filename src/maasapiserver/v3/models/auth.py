from pydantic import BaseModel

from maasapiserver.v3.auth.jwt import UserRole


class AuthenticatedUser(BaseModel):
    username: str
    roles: set[UserRole]
