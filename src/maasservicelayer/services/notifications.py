# Copyright 2025 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

import structlog

from maascommon.logging.security import AUTHZ_ADMIN, SECURITY
from maasservicelayer.builders.notifications import NotificationBuilder
from maasservicelayer.context import Context
from maasservicelayer.db.repositories.notifications import (
    NotificationsRepository,
)
from maasservicelayer.exceptions.catalog import (
    BadRequestException,
    BaseExceptionDetail,
    NotFoundException,
)
from maasservicelayer.exceptions.constants import (
    PRECONDITION_FAILED,
    UNEXISTING_RESOURCE_VIOLATION_TYPE,
)
from maasservicelayer.models.auth import AuthenticatedUser
from maasservicelayer.models.base import ListResult
from maasservicelayer.models.notifications import Notification
from maasservicelayer.services.base import BaseService, ServiceCache

logger = structlog.getLogger()


class NotificationsService(
    BaseService[Notification, NotificationsRepository, NotificationBuilder]
):
    def __init__(
        self,
        context: Context,
        repository: NotificationsRepository,
        cache: ServiceCache | None = None,
    ):
        super().__init__(context, repository, cache)

    async def list_all_for_user(
        self, page: int, size: int, user: AuthenticatedUser
    ) -> ListResult[Notification]:
        return await self.repository.list_all_for_user(
            page=page, size=size, user_id=user.id, is_admin=user.is_admin()
        )

    async def list_active_for_user(
        self, page: int, size: int, user: AuthenticatedUser
    ) -> ListResult[Notification]:
        return await self.repository.list_active_for_user(
            page=page, size=size, user_id=user.id, is_admin=user.is_admin()
        )

    async def get_by_id_for_user(
        self, notification_id: int, user: AuthenticatedUser
    ) -> Notification | None:
        return await self.repository.get_by_id_for_user(
            notification_id=notification_id,
            user_id=user.id,
            is_admin=user.is_admin(),
        )

    async def dismiss(
        self, notification_id: int, user: AuthenticatedUser
    ) -> None:
        notification = await self.get_by_id_for_user(notification_id, user)
        if notification is None:
            raise NotFoundException(
                details=[
                    BaseExceptionDetail(
                        type=UNEXISTING_RESOURCE_VIOLATION_TYPE,
                        message=f"Notification with id {notification_id} does not exist.",
                    )
                ]
            )
        if not notification.dismissable:
            raise BadRequestException(
                details=[
                    BaseExceptionDetail(
                        type=PRECONDITION_FAILED,
                        message="The notification is not dismissable.",
                    )
                ]
            )
        return await self.repository.create_notification_dismissal(
            notification_id=notification_id,
            user_id=user.id,
        )

    async def post_create_hook(self, resource):
        logger.info(
            f"{AUTHZ_ADMIN}:notification:created:{resource.id}",
            type=SECURITY,
        )

    async def post_update_hook(self, old_resource, updated_resource):
        logger.info(
            f"{AUTHZ_ADMIN}:notification:updated:{updated_resource.id}",
            type=SECURITY,
        )

    async def post_update_many_hook(self, resources):
        resource_ids = [resource.id for resource in resources]
        logger.info(
            f"{AUTHZ_ADMIN}:notifications:updated:{resource_ids}",
            type=SECURITY,
        )

    async def post_delete_hook(self, resource):
        logger.info(
            f"{AUTHZ_ADMIN}:notification:deleted:{resource.id}",
            type=SECURITY,
        )

    async def post_delete_many_hook(self, resources):
        resource_ids = [resource.id for resource in resources]
        logger.info(
            f"{AUTHZ_ADMIN}:notifications:deleted:{resource_ids}",
            type=SECURITY,
        )
