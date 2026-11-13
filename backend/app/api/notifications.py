from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.async_security import require_async_roles
from app.core.database import get_async_db
from app.core.responses import APIResponse
from app.schemas.notification import (
    NotificationListResponse,
    NotificationResponse,
    NotificationUnreadCountResponse,
)
from app.services.async_notification_service import AsyncNotificationService
from app.utils.constants import DEFAULT_PAGE, DEFAULT_PAGE_SIZE
from app.utils.enums import NotificationStatus, UserRole

router = APIRouter(prefix="/api/v1/notifications", tags=["Notifications"])
_NOTIFICATION_ROLES = (
    UserRole.ADMINISTRATOR,
    UserRole.COMPLIANCE_OFFICER,
    UserRole.REVIEWER,
    UserRole.AUDITOR,
)


def _service(
    db: AsyncSession, current_user: dict[str, Any]
) -> AsyncNotificationService:
    return AsyncNotificationService(db, UUID(current_user["tenant_id"]))


@router.get("", response_model=APIResponse[NotificationListResponse])
async def list_notifications(
    status: NotificationStatus | None = Query(default=None),
    page: int = Query(default=DEFAULT_PAGE, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(*_NOTIFICATION_ROLES, resource_type="notification")
    ),
) -> APIResponse[NotificationListResponse]:
    result = await _service(db, current_user).list_notifications(
        user_id=UUID(current_user["sub"]),
        status=status,
        page=page,
        page_size=page_size,
    )
    return APIResponse(
        success=True, message="Notifications retrieved successfully.", data=result
    )


@router.get(
    "/unread-count", response_model=APIResponse[NotificationUnreadCountResponse]
)
async def unread_count(
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(*_NOTIFICATION_ROLES, resource_type="notification")
    ),
) -> APIResponse[NotificationUnreadCountResponse]:
    count = await _service(db, current_user).get_unread_count(
        user_id=UUID(current_user["sub"])
    )
    return APIResponse(
        success=True,
        message="Unread notification count retrieved successfully.",
        data=NotificationUnreadCountResponse(unread_count=count),
    )


@router.get("/{notification_id}", response_model=APIResponse[NotificationResponse])
async def get_notification(
    notification_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(*_NOTIFICATION_ROLES, resource_type="notification")
    ),
) -> APIResponse[NotificationResponse]:
    notification = await _service(db, current_user).get_notification(
        notification_id=notification_id, user_id=UUID(current_user["sub"])
    )
    return APIResponse(
        success=True,
        message="Notification retrieved successfully.",
        data=NotificationResponse.model_validate(notification),
    )


@router.patch(
    "/{notification_id}/read", response_model=APIResponse[NotificationResponse]
)
async def mark_notification_as_read(
    notification_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(*_NOTIFICATION_ROLES, resource_type="notification")
    ),
) -> APIResponse[NotificationResponse]:
    notification = await _service(db, current_user).mark_as_read(
        notification_id=notification_id, user_id=UUID(current_user["sub"])
    )
    return APIResponse(
        success=True,
        message="Notification marked as read.",
        data=NotificationResponse.model_validate(notification),
    )
