from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.core.dependencies import get_notification_service
from app.core.responses import APIResponse
from app.core.security import require_roles
from app.schemas.notification import (
    NotificationListResponse,
    NotificationResponse,
    NotificationUnreadCountResponse,
)
from app.services.notification_service import NotificationService
from app.utils.constants import DEFAULT_PAGE, DEFAULT_PAGE_SIZE
from app.utils.enums import NotificationStatus, UserRole

router = APIRouter(
    prefix="/api/v1/notifications",
    tags=["Notifications"],
)


_NOTIFICATION_ROLES = (
    UserRole.ADMINISTRATOR,
    UserRole.COMPLIANCE_OFFICER,
    UserRole.REVIEWER,
    UserRole.AUDITOR,
)


@router.get(
    "",
    response_model=APIResponse[NotificationListResponse],
)
def list_notifications(
    status: NotificationStatus | None = Query(
        default=None,
    ),
    page: int = Query(
        default=DEFAULT_PAGE,
        ge=1,
    ),
    page_size: int = Query(
        default=DEFAULT_PAGE_SIZE,
        ge=1,
    ),
    notification_service: NotificationService = Depends(
        get_notification_service,
    ),
    current_user: dict[str, Any] = Depends(
        require_roles(*_NOTIFICATION_ROLES, resource_type="notification")
    ),
):
    result = notification_service.list_notifications(
        user_id=UUID(current_user["sub"]),
        status=status,
        page=page,
        page_size=page_size,
    )

    return APIResponse(
        success=True,
        message="Notifications retrieved successfully.",
        data=result,
    )


@router.get(
    "/unread-count",
    response_model=APIResponse[NotificationUnreadCountResponse],
)
def unread_count(
    notification_service: NotificationService = Depends(
        get_notification_service,
    ),
    current_user: dict[str, Any] = Depends(
        require_roles(*_NOTIFICATION_ROLES, resource_type="notification")
    ),
):
    count = notification_service.get_unread_count(
        user_id=UUID(current_user["sub"]),
    )

    return APIResponse(
        success=True,
        message="Unread notification count retrieved successfully.",
        data=NotificationUnreadCountResponse(
            unread_count=count,
        ),
    )


@router.get(
    "/{notification_id}",
    response_model=APIResponse[NotificationResponse],
)
def get_notification(
    notification_id: UUID,
    notification_service: NotificationService = Depends(
        get_notification_service,
    ),
    current_user: dict[str, Any] = Depends(
        require_roles(*_NOTIFICATION_ROLES, resource_type="notification")
    ),
):
    notification = notification_service.get_notification(
        notification_id=notification_id,
        user_id=UUID(current_user["sub"]),
    )

    return APIResponse(
        success=True,
        message="Notification retrieved successfully.",
        data=notification,
    )


@router.patch(
    "/{notification_id}/read",
    response_model=APIResponse[NotificationResponse],
)
def mark_notification_as_read(
    notification_id: UUID,
    notification_service: NotificationService = Depends(
        get_notification_service,
    ),
    current_user: dict[str, Any] = Depends(
        require_roles(*_NOTIFICATION_ROLES, resource_type="notification")
    ),
):
    notification = notification_service.mark_as_read(
        notification_id=notification_id,
        user_id=UUID(current_user["sub"]),
    )

    return APIResponse(
        success=True,
        message="Notification marked as read.",
        data=notification,
    )
