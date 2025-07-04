#  Copyright 2024-2025 Canonical Ltd.  This software is licensed under the
#  GNU Affero General Public License version 3 (see the file LICENSE).

import json
from json import dumps as _dumps
from unittest.mock import Mock, patch

from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from httpx import AsyncClient
from macaroonbakery.bakery import Macaroon
import pytest

from maasapiserver.common.api.models.responses.errors import ErrorBodyResponse
from maasapiserver.v3.api.public.models.requests.users import (
    UserCreateRequest,
    UserUpdateRequest,
)
from maasapiserver.v3.api.public.models.responses.users import (
    UserInfoResponse,
    UserResponse,
    UsersListResponse,
    UsersWithSummaryListResponse,
    UserWithSummaryResponse,
)
from maasapiserver.v3.constants import V3_API_PREFIX
from maasservicelayer.db.filters import QuerySpec
from maasservicelayer.db.repositories.users import UserClauseFactory
from maasservicelayer.exceptions.catalog import (
    AlreadyExistsException,
    BadRequestException,
    BaseExceptionDetail,
    DischargeRequiredException,
    NotFoundException,
    PreconditionFailedException,
)
from maasservicelayer.exceptions.constants import (
    ETAG_PRECONDITION_VIOLATION_TYPE,
    INVALID_ARGUMENT_VIOLATION_TYPE,
    PRECONDITION_FAILED,
    UNIQUE_CONSTRAINT_VIOLATION_TYPE,
)
from maasservicelayer.models.base import ListResult
from maasservicelayer.models.users import User, UserProfile, UserWithSummary
from maasservicelayer.services import ServiceCollectionV3
from maasservicelayer.services.external_auth import ExternalAuthService
from maasservicelayer.services.users import UsersService
from maasservicelayer.utils.date import utcnow
from tests.maasapiserver.v3.api.public.handlers.base import (
    ApiCommonTests,
    Endpoint,
)

USER_1 = User(
    id=1,
    username="username",
    password="pass",
    is_superuser=False,
    first_name="",
    last_name="",
    is_staff=False,
    is_active=True,
    date_joined=utcnow(),
    email="username@example.com",
    last_login=None,
)

USER_2 = User(
    id=2,
    username="username2",
    password="pass2",
    is_superuser=False,
    first_name="Bob",
    last_name="Guy",
    is_staff=False,
    is_active=True,
    date_joined=utcnow(),
    email="bob@company.com",
    last_login=None,
)


@pytest.mark.asyncio
class TestUsersApi(ApiCommonTests):
    BASE_PATH = f"{V3_API_PREFIX}/users"

    @pytest.fixture
    def user_endpoints(self) -> list[Endpoint]:
        return [
            Endpoint(method="GET", path=f"{self.BASE_PATH}/me"),
            Endpoint(
                method="POST", path=f"{self.BASE_PATH}/me:complete_intro"
            ),
            Endpoint(
                method="POST", path=f"{self.BASE_PATH}/me:change_password"
            ),
        ]

    @pytest.fixture
    def admin_endpoints(self) -> list[Endpoint]:
        return [
            Endpoint(method="GET", path=f"{self.BASE_PATH}"),
            Endpoint(method="GET", path=f"{self.BASE_PATH}/1"),
            Endpoint(method="GET", path=f"{V3_API_PREFIX}/users_with_summary"),
            Endpoint(method="POST", path=f"{self.BASE_PATH}"),
            Endpoint(method="PUT", path=f"{self.BASE_PATH}/1"),
            Endpoint(method="DELETE", path=f"{self.BASE_PATH}/1"),
            Endpoint(
                method="POST", path=f"{self.BASE_PATH}/1:change_password"
            ),
        ]

    # GET /users/me
    async def test_get_user_info(
        self,
        services_mock: ServiceCollectionV3,
        mocked_api_client_user: AsyncClient,
    ) -> None:
        services_mock.users = Mock(UsersService)
        services_mock.users.get_one.return_value = User(
            id=1,
            username="username",
            password="pass",
            is_superuser=False,
            first_name="",
            last_name="",
            is_staff=False,
            is_active=True,
            date_joined=utcnow(),
            email=None,
            last_login=None,
        )
        response = await mocked_api_client_user.get(
            f"{self.BASE_PATH}/me",
        )
        assert response.status_code == 200

        user_info = UserInfoResponse(**response.json())
        assert user_info.id == 1
        assert user_info.username == "username"
        assert user_info.is_superuser is False

    async def test_get_user_info_admin(
        self,
        services_mock: ServiceCollectionV3,
        mocked_api_client_admin: AsyncClient,
    ) -> None:
        services_mock.users = Mock(UsersService)
        services_mock.users.get_one.return_value = User(
            id=1,
            username="admin",
            password="pass",
            is_superuser=True,
            first_name="",
            last_name="",
            is_staff=True,
            is_active=True,
            date_joined=utcnow(),
            email=None,
            last_login=None,
        )
        response = await mocked_api_client_admin.get(
            f"{self.BASE_PATH}/me",
        )
        assert response.status_code == 200

        user_info = UserInfoResponse(**response.json())
        assert user_info.id == 1
        assert user_info.username == "admin"
        assert user_info.is_superuser is True

    async def test_get_user_info_unauthorized(
        self, mocked_api_client: AsyncClient
    ) -> None:
        response = await mocked_api_client.get(f"{self.BASE_PATH}/me")
        assert response.status_code == 401
        error_response = ErrorBodyResponse(**response.json())
        assert error_response.kind == "Error"
        assert error_response.code == 401

    async def test_get_user_info_discharge_required(
        self,
        services_mock: ServiceCollectionV3,
        mocked_api_client_rbac: AsyncClient,
    ) -> None:
        """If external auth is enabled make sure we receive a discharge required response"""
        services_mock.external_auth = Mock(ExternalAuthService)
        services_mock.external_auth.raise_discharge_required_exception.side_effect = DischargeRequiredException(
            macaroon=Mock(Macaroon)
        )

        # we have to mock json.dumps as it doesn't know how to deal with Mock objects
        def custom_json_dumps(*args, **kwargs):
            return _dumps(*args, **(kwargs | {"default": lambda obj: "mock"}))

        with patch("json.dumps", custom_json_dumps):
            response = await mocked_api_client_rbac.get(f"{self.BASE_PATH}/me")

        assert response.status_code == 401
        discharge_response = json.loads(response.content.decode("utf-8"))
        assert discharge_response["Code"] == "macaroon discharge required"
        assert discharge_response["Info"]["Macaroon"] is not None
        assert discharge_response["Info"]["MacaroonPath"] == "/"
        assert discharge_response["Info"]["CookieNameSuffix"] == "maas"

    # GET /users
    async def test_list_users_has_other_page(
        self,
        services_mock: ServiceCollectionV3,
        mocked_api_client_admin: AsyncClient,
    ) -> None:
        services_mock.users = Mock(UsersService)
        services_mock.users.list.return_value = ListResult[User](
            items=[USER_1], total=2
        )
        response = await mocked_api_client_admin.get(
            f"{self.BASE_PATH}?size=1",
        )

        assert response.status_code == 200
        users_response = UsersListResponse(**response.json())
        assert len(users_response.items) == 1
        assert users_response.total == 2
        assert users_response.next == f"{self.BASE_PATH}?page=2&size=1"

    async def test_list_users_no_other_page(
        self,
        services_mock: ServiceCollectionV3,
        mocked_api_client_admin: AsyncClient,
    ) -> None:
        services_mock.users = Mock(UsersService)
        services_mock.users.list.return_value = ListResult[User](
            items=[USER_1, USER_2], total=2
        )
        response = await mocked_api_client_admin.get(
            f"{self.BASE_PATH}?size=2",
        )

        assert response.status_code == 200
        users_response = UsersListResponse(**response.json())
        assert len(users_response.items) == 2
        assert users_response.total == 2
        assert users_response.next is None

    # GET /users/{user_id}
    async def test_get_user(
        self,
        services_mock: ServiceCollectionV3,
        mocked_api_client_admin: AsyncClient,
    ) -> None:
        services_mock.users = Mock(UsersService)
        services_mock.users.get_by_id.return_value = USER_1
        response = await mocked_api_client_admin.get(
            f"{self.BASE_PATH}/1",
        )
        assert response.status_code == 200
        assert len(response.headers["ETag"]) > 0
        user_response = UserResponse(**response.json())
        assert user_response.id == 1
        assert user_response.username == "username"

    async def test_get_user_404(
        self,
        services_mock: ServiceCollectionV3,
        mocked_api_client_admin: AsyncClient,
    ) -> None:
        services_mock.users = Mock(UsersService)
        services_mock.users.get_by_id.return_value = None
        response = await mocked_api_client_admin.get(
            f"{self.BASE_PATH}/99",
        )
        assert response.status_code == 404
        assert "ETag" not in response.headers

        error_response = ErrorBodyResponse(**response.json())
        assert error_response.kind == "Error"
        assert error_response.code == 404

    async def test_get_user_422(
        self,
        services_mock: ServiceCollectionV3,
        mocked_api_client_admin: AsyncClient,
    ) -> None:
        services_mock.users = Mock(UsersService)
        services_mock.users.get_one.side_effect = RequestValidationError(
            errors=[]
        )
        response = await mocked_api_client_admin.get(
            f"{self.BASE_PATH}/1a",
        )
        assert response.status_code == 422
        assert "ETag" not in response.headers

        error_response = ErrorBodyResponse(**response.json())
        assert error_response.kind == "Error"
        assert error_response.code == 422

    # POST /users/{user_id}
    async def test_post_user(
        self,
        services_mock: ServiceCollectionV3,
        mocked_api_client_admin: AsyncClient,
    ) -> None:
        create_user_request = UserCreateRequest(
            username="new_username",
            password="new_password",
            is_superuser=False,
            first_name="new_first_name",
            last_name="new_last_name",
            email="new_user@example.com",
        )
        new_user = User(
            id=3,
            username="new_username",
            password="new_password",
            is_superuser=False,
            is_staff=False,
            is_active=False,
            first_name="new_first_name",
            last_name="new_last_name",
            email="new_user@example.com",
            date_joined=utcnow(),
        )

        services_mock.users = Mock(UsersService)
        services_mock.users.create.return_value = new_user

        response = await mocked_api_client_admin.post(
            self.BASE_PATH, json=jsonable_encoder(create_user_request)
        )

        assert response.status_code == 201
        assert len(response.headers["ETag"]) > 0

        user_response = UserResponse(**response.json())

        assert user_response.id == new_user.id
        assert user_response.is_superuser == new_user.is_superuser
        assert user_response.username == new_user.username
        assert user_response.first_name == new_user.first_name
        assert user_response.last_name == new_user.last_name
        assert user_response.email == new_user.email
        assert user_response.date_joined == new_user.date_joined

    async def test_post_user_409(
        self,
        services_mock: ServiceCollectionV3,
        mocked_api_client_admin: AsyncClient,
    ) -> None:
        create_user_request = UserCreateRequest(
            username="new_username",
            password="new_password",
            is_superuser=False,
            first_name="new_first_name",
            last_name="new_last_name",
            email="new_user@example.com",
        )
        new_user = User(
            id=3,
            username="new_username",
            password="new_password",
            is_superuser=False,
            is_staff=False,
            is_active=False,
            first_name="new_first_name",
            last_name="new_last_name",
            email="new_user@example.com",
            date_joined=utcnow(),
        )

        services_mock.users = Mock(UsersService)
        services_mock.users.create.side_effect = [
            new_user,
            AlreadyExistsException(
                details=[
                    BaseExceptionDetail(
                        type=UNIQUE_CONSTRAINT_VIOLATION_TYPE,
                        message="A resource with such identifiers already exist.",
                    )
                ]
            ),
        ]

        response = await mocked_api_client_admin.post(
            self.BASE_PATH, json=jsonable_encoder(create_user_request)
        )
        assert response.status_code == 201

        response = await mocked_api_client_admin.post(
            self.BASE_PATH, json=jsonable_encoder(create_user_request)
        )
        assert response.status_code == 409

        error_response = ErrorBodyResponse(**response.json())
        assert error_response.kind == "Error"
        assert error_response.code == 409
        assert len(error_response.details) == 1
        assert error_response.details[0].type == "UniqueConstraintViolation"
        assert "already exist" in error_response.details[0].message

    @pytest.mark.parametrize("user_request", [{"username": None}])
    async def test_post_user_422(
        self,
        services_mock: ServiceCollectionV3,
        mocked_api_client_admin: AsyncClient,
        user_request: dict[str, str],
    ) -> None:
        services_mock.users = Mock(UsersService)
        services_mock.users.create.return_value = None

        response = await mocked_api_client_admin.post(
            self.BASE_PATH, json=jsonable_encoder(user_request)
        )

        assert response.status_code == 422
        assert "ETag" not in response.headers

        error_response = ErrorBodyResponse(**response.json())

        assert error_response.kind == "Error"
        assert error_response.code == 422

    # PUT /users/{user_id}
    async def test_put_user(
        self,
        services_mock: ServiceCollectionV3,
        mocked_api_client_admin: AsyncClient,
    ) -> None:
        updated_user = User(
            id=1,
            is_active=False,
            is_superuser=True,
            is_staff=False,
            username="new_user",
            password="new_pass",
            first_name="new_first_name",
            last_name="new_last_name",
            email="new_email@example.com",
        )
        services_mock.users = Mock(UsersService)
        services_mock.users.update_by_id.return_value = updated_user

        user_request = UserUpdateRequest(
            is_superuser=True,
            username="new_user",
            password="new_pass",
            first_name="new_first_name",
            last_name="new_last_name",
            email="new_email@example.com",
        )

        response = await mocked_api_client_admin.put(
            f"{self.BASE_PATH}/1",
            json=jsonable_encoder(user_request),
        )

        assert response.status_code == 200

        user_response = UserResponse(**response.json())

        assert user_response.id == updated_user.id
        assert user_response.is_superuser == updated_user.is_superuser
        assert user_response.username == updated_user.username
        assert user_response.first_name == updated_user.first_name
        assert user_response.last_name == updated_user.last_name
        assert user_response.email == updated_user.email

    async def test_put_user_404(
        self,
        services_mock: ServiceCollectionV3,
        mocked_api_client_admin: AsyncClient,
    ) -> None:
        services_mock.users = Mock(UsersService)
        services_mock.users.update_by_id.side_effect = NotFoundException()

        user_request = UserUpdateRequest(
            is_superuser=True,
            username="new_user",
            password="new_pass",
            first_name="new_first_name",
            last_name="new_last_name",
            email="new_email@example.com",
        )

        response = await mocked_api_client_admin.put(
            f"{self.BASE_PATH}/99",
            json=jsonable_encoder(user_request),
        )

        assert response.status_code == 404
        assert "ETag" not in response.headers

        error_response = ErrorBodyResponse(**response.json())

        assert error_response.kind == "Error"
        assert error_response.code == 404

    async def test_put_user_422(
        self,
        services_mock: ServiceCollectionV3,
        mocked_api_client_admin: AsyncClient,
    ) -> None:
        services_mock.users = Mock(UsersService)
        services_mock.users.update_by_id.return_value = None

        user_request = UserUpdateRequest(
            is_superuser=True,
            username="new_user",
            password="new_pass",
            first_name="new_first_name",
            last_name="new_last_name",
            email="new_email@example.com",
        )

        response = await mocked_api_client_admin.put(
            f"{self.BASE_PATH}/A1",
            json=jsonable_encoder(user_request),
        )

        assert response.status_code == 422
        assert "ETag" not in response.headers

        error_response = ErrorBodyResponse(**response.json())

        assert error_response.kind == "Error"
        assert error_response.code == 422

    async def test_delete_204(
        self,
        services_mock: ServiceCollectionV3,
        mocked_api_client_admin: AsyncClient,
    ) -> None:
        services_mock.users = Mock(UsersService)
        services_mock.users.get_by_id.return_value = USER_1
        services_mock.users.delete_by_id.return_value = USER_1

        response = await mocked_api_client_admin.delete(f"{self.BASE_PATH}/1")
        assert response.status_code == 204

    async def test_delete_404(
        self,
        services_mock: ServiceCollectionV3,
        mocked_api_client_admin: AsyncClient,
    ) -> None:
        services_mock.users = Mock(UsersService)
        services_mock.users.exists.return_value = False

        response = await mocked_api_client_admin.delete(f"{self.BASE_PATH}/1")
        assert response.status_code == 404

    async def test_delete_with_etag(
        self,
        services_mock: ServiceCollectionV3,
        mocked_api_client_admin: AsyncClient,
    ) -> None:
        services_mock.users = Mock(UsersService)
        services_mock.users.exists.return_value = True
        services_mock.users.delete_by_id.side_effect = PreconditionFailedException(
            details=[
                BaseExceptionDetail(
                    type=ETAG_PRECONDITION_VIOLATION_TYPE,
                    message="The resource etag 'wrong_etag' did not match 'my_etag'.",
                )
            ]
        )

        response = await mocked_api_client_admin.delete(
            f"{self.BASE_PATH}/1", headers={"if-match": "wrong_etag"}
        )
        assert response.status_code == 412
        services_mock.users.exists.assert_called_with(
            query=QuerySpec(UserClauseFactory.with_id(USER_1.id))
        )
        services_mock.users.delete_by_id.assert_called_with(
            USER_1.id,
            etag_if_match="wrong_etag",
        )

    async def test_delete_self(
        self,
        services_mock: ServiceCollectionV3,
        mocked_api_client_admin: AsyncClient,
    ) -> None:
        user = USER_1.copy()
        # the api client we use has an authenticated user with id=0
        user.id = 0
        services_mock.users = Mock(UsersService)
        services_mock.users.get_by_id.return_value = user

        response = await mocked_api_client_admin.delete(f"{self.BASE_PATH}/0")
        assert response.status_code == 400

    async def test_delete_with_resources_allocated(
        self,
        services_mock: ServiceCollectionV3,
        mocked_api_client_admin: AsyncClient,
    ) -> None:
        services_mock.users = Mock(UsersService)
        services_mock.users.get_by_id.return_value = USER_1
        services_mock.users.delete_by_id.side_effect = PreconditionFailedException(
            details=[
                BaseExceptionDetail(
                    type=PRECONDITION_FAILED,
                    message="Cannot delete user. 2 node(s) are still allocated.",
                )
            ]
        )
        response = await mocked_api_client_admin.delete(f"{self.BASE_PATH}/1")
        assert response.status_code == 412

    async def test_delete_with_transfer_resources(
        self,
        services_mock: ServiceCollectionV3,
        mocked_api_client_admin: AsyncClient,
    ) -> None:
        services_mock.users = Mock(UsersService)
        services_mock.users.get_by_id.return_value = USER_1
        services_mock.users.transfer_resources.return_value = None
        services_mock.users.delete_by_id.return_value = USER_1

        response = await mocked_api_client_admin.delete(
            f"{self.BASE_PATH}/1", params={"transfer_resources_to": 2}
        )
        assert response.status_code == 204
        services_mock.users.transfer_resources.assert_called_once_with(1, 2)

    async def test_delete_with_transfer_resources_nonexistent_user(
        self,
        services_mock: ServiceCollectionV3,
        mocked_api_client_admin: AsyncClient,
    ) -> None:
        services_mock.users = Mock(UsersService)
        services_mock.users.get_by_id.return_value = USER_1
        services_mock.users.transfer_resources.side_effect = BadRequestException(
            details=[
                BaseExceptionDetail(
                    type=INVALID_ARGUMENT_VIOLATION_TYPE,
                    message="Cannot transfer resources. User with id 2 doesn't exist.",
                )
            ]
        )

        response = await mocked_api_client_admin.delete(
            f"{self.BASE_PATH}/1", params={"transfer_resources_to": 2}
        )
        assert response.status_code == 400
        services_mock.users.transfer_resources.assert_called_once_with(1, 2)

    async def test_list_with_summary(
        self,
        services_mock: ServiceCollectionV3,
        mocked_api_client_admin: AsyncClient,
    ) -> None:
        services_mock.users = Mock(UsersService)
        services_mock.users.list_with_summary.return_value = ListResult[
            UserWithSummary
        ](
            items=[
                UserWithSummary(
                    id=1,
                    username="foo",
                    completed_intro=True,
                    email="foo@example.com",
                    is_local=True,
                    is_superuser=False,
                    last_name="foo",
                    machines_count=2,
                    sshkeys_count=3,
                )
            ],
            total=1,
        )

        response = await mocked_api_client_admin.get(
            f"{V3_API_PREFIX}/users_with_summary?size=1",
        )
        assert response.status_code == 200
        users_with_summary = UsersWithSummaryListResponse(**response.json())
        assert users_with_summary.total == 1
        assert len(users_with_summary.items) == 1
        assert users_with_summary.next is None
        user = users_with_summary.items[0]
        assert user.id == 1
        assert user.username == "foo"
        assert user.completed_intro is True
        assert user.is_local is True
        assert user.is_superuser is False
        assert user.last_name == "foo"
        assert user.machines_count == 2
        assert user.sshkeys_count == 3
        services_mock.users.list_with_summary.assert_called_once_with(
            page=1, size=1, query=QuerySpec(where=None)
        )

    async def test_list_with_summary_filters(
        self,
        services_mock: ServiceCollectionV3,
        mocked_api_client_admin: AsyncClient,
    ) -> None:
        services_mock.users = Mock(UsersService)
        services_mock.users.list_with_summary.return_value = ListResult[
            UserWithSummary
        ](
            items=[
                UserWithSummary(
                    id=1,
                    username="foo",
                    completed_intro=True,
                    email="foo@example.com",
                    is_local=True,
                    is_superuser=False,
                    last_name="foo",
                    machines_count=2,
                    sshkeys_count=3,
                )
            ],
            total=2,
        )

        response = await mocked_api_client_admin.get(
            f"{V3_API_PREFIX}/users_with_summary?size=1&username_or_email=example",
        )
        assert response.status_code == 200
        users_with_summary = UsersWithSummaryListResponse(**response.json())
        assert users_with_summary.total == 2
        assert len(users_with_summary.items) == 1
        assert (
            users_with_summary.next
            == f"{V3_API_PREFIX}/users_with_summary?page=2&size=1&username_or_email=example"
        )
        services_mock.users.list_with_summary.assert_called_once_with(
            page=1,
            size=1,
            query=QuerySpec(
                where=UserClauseFactory.with_username_or_email_like("example")
            ),
        )

    async def test_complete_intro(
        self,
        services_mock: ServiceCollectionV3,
        mocked_api_client_user: AsyncClient,
    ) -> None:
        services_mock.users = Mock(UsersService)
        services_mock.users.complete_intro.return_value = Mock(UserProfile)

        response = await mocked_api_client_user.post(
            f"{V3_API_PREFIX}/users/me:complete_intro"
        )
        assert response.status_code == 204

        # the user we use in tests has the id=0
        services_mock.users.complete_intro.assert_called_once_with(0)

    async def test_change_password_user(
        self,
        services_mock: ServiceCollectionV3,
        mocked_api_client_user: AsyncClient,
    ) -> None:
        services_mock.users = Mock(UsersService)
        services_mock.users.change_password.return_value = None

        json = {"password": "foo"}

        response = await mocked_api_client_user.post(
            f"{V3_API_PREFIX}/users/me:change_password", json=json
        )
        assert response.status_code == 204

        # the user we use in tests has the id=0
        services_mock.users.change_password.assert_called_once_with(
            user_id=0, password="foo"
        )

    async def test_change_password_admin(
        self,
        services_mock: ServiceCollectionV3,
        mocked_api_client_admin: AsyncClient,
    ) -> None:
        services_mock.users = Mock(UsersService)
        services_mock.users.change_password.return_value = None

        json = {"password": "foo"}

        response = await mocked_api_client_admin.post(
            f"{V3_API_PREFIX}/users/1:change_password", json=json
        )
        assert response.status_code == 204

        services_mock.users.change_password.assert_called_once_with(
            user_id=1, password="foo"
        )

    async def test_user_with_summary(
        self,
        services_mock: ServiceCollectionV3,
        mocked_api_client_user: AsyncClient,
    ) -> None:
        services_mock.users = Mock(UsersService)
        services_mock.users.get_by_id_with_summary.return_value = (
            UserWithSummary(
                id=0,
                username="foo",
                completed_intro=True,
                email="foo@example.com",
                is_local=True,
                is_superuser=False,
                last_name="foo",
                machines_count=2,
                sshkeys_count=3,
            )
        )

        response = await mocked_api_client_user.get(
            f"{V3_API_PREFIX}/users/me_with_summary"
        )
        assert response.status_code == 200
        user_with_summary = UserWithSummaryResponse(**response.json())
        assert user_with_summary.id == 0
        assert user_with_summary.username == "foo"
        services_mock.users.get_by_id_with_summary.assert_called_once_with(
            id=0
        )
