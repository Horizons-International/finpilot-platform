from typing import Any, Callable
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.async_security import require_async_roles
from app.core.database import get_async_db
from app.core.responses import APIResponse
from app.schemas.notification import (
    NotificationListResponse,
    NotificationResponse,
    NotificationUnreadCountResponse,
)
from app.services.async_service_bridge import run_sync_in_tenant
from app.services.notification_service import NotificationService
from app.utils.constants import DEFAULT_PAGE, DEFAULT_PAGE_SIZE
from app.utils.enums import NotificationStatus, UserRole

router = APIRouter(prefix="/api/v1/notifications", tags=["Notifications"])

_NOTIFICATION_ROLES = (
    UserRole.ADMINISTRATOR,
    UserRole.COMPLIANCE_OFFICER,
    UserRole.REVIEWER,
    UserRole.AUDITOR,
)


async def _notification_operation(
    db: AsyncSession,
    current_user: dict[str, Any],
    operation: Callable[[NotificationService], Any],
) -> Any:
    tenant_id = UUID(current_user["tenant_id"])

    def invoke(sync_db: Session):
        service = NotificationService(sync_db, tenant_id=tenant_id)
        return operation(service)

    return await run_sync_in_tenant(db, tenant_id, invoke)


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
    result = await _notification_operation(
        db,
        current_user,
        lambda service: service.list_notifications(
            user_id=UUID(current_user["sub"]),
            status=status,
            page=page,
            page_size=page_size,
        ),
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
    count = await _notification_operation(
        db,
        current_user,
        lambda service: service.get_unread_count(user_id=UUID(current_user["sub"])),
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
    notification = await _notification_operation(
        db,
        current_user,
        lambda service: NotificationResponse.model_validate(
            service.get_notification(
                notification_id=notification_id,
                user_id=UUID(current_user["sub"]),
            )
        ),
    )
    return APIResponse(
        success=True, message="Notification retrieved successfully.", data=notification
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
    notification = await _notification_operation(
        db,
        current_user,
        lambda service: NotificationResponse.model_validate(
            service.mark_as_read(
                notification_id=notification_id,
                user_id=UUID(current_user["sub"]),
            )
        ),
    )
    return APIResponse(
        success=True, message="Notification marked as read.", data=notification
    )
