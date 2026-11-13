"""Native-async notification creation and user-facing operations."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification, NotificationDelivery
from app.repositories.async_notification_repository import AsyncNotificationRepository
from app.schemas.notification import (
    NotificationListResponse,
    NotificationResponse,
)
from app.utils.date_time import utc_now
from app.utils.enums import (
    NotificationChannel,
    NotificationDeliveryStatus,
    NotificationEventType,
    NotificationStatus,
)
from app.utils.errors import bad_request, not_found
from app.utils.pagination import validate_pagination


class AsyncNotificationService:
    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        active_tenant = db.info.get("tenant_id")
        if active_tenant is not None and active_tenant != tenant_id:
            raise ValueError(
                "Notification service tenant does not match session tenant."
            )
        db.info["tenant_id"] = tenant_id
        self.db = db
        self.tenant_id = tenant_id
        self.repository = AsyncNotificationRepository(db, tenant_id)

    async def create_notification(
        self,
        *,
        user_id: UUID,
        title: str,
        message: str,
        event_type: NotificationEventType,
        resource_type: str | None = None,
        resource_id: UUID | None = None,
        channels: Sequence[NotificationChannel] = (NotificationChannel.IN_APP,),
    ) -> Notification:
        user = await self.repository.ensure_recipient(user_id)
        if user is None:
            raise not_found("Notification recipient")
        if user.is_deleted:
            raise bad_request("Cannot create a notification for a deleted user.")

        normalized_title = title.strip()
        normalized_message = message.strip()
        if not normalized_title:
            raise bad_request("Notification title is required.")
        if not normalized_message:
            raise bad_request("Notification message is required.")

        notification = Notification(
            tenant_id=self.tenant_id,
            user_id=user_id,
            title=normalized_title,
            message=normalized_message,
            status=NotificationStatus.UNREAD,
            event_type=event_type.value,
            resource_type=resource_type,
            resource_id=resource_id,
        )
        notification = await self.repository.create(notification)
        for channel in dict.fromkeys(channels):
            delivered = channel == NotificationChannel.IN_APP
            self.db.add(
                NotificationDelivery(
                    tenant_id=self.tenant_id,
                    notification_id=notification.id,
                    channel=channel,
                    status=(
                        NotificationDeliveryStatus.DELIVERED
                        if delivered
                        else NotificationDeliveryStatus.PENDING
                    ),
                    delivered_at=utc_now() if delivered else None,
                )
            )
        await self.db.flush()
        await self.db.refresh(notification, attribute_names=["deliveries"])
        return notification

    async def list_notifications(
        self,
        *,
        user_id: UUID,
        status: NotificationStatus | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> NotificationListResponse:
        validate_pagination(page, page_size)
        notifications, total = await self.repository.list_for_user(
            user_id=user_id, status=status, page=page, page_size=page_size
        )
        return NotificationListResponse(
            notifications=[
                NotificationResponse.model_validate(item) for item in notifications
            ],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=(total + page_size - 1) // page_size if total else 0,
        )

    async def get_notification(
        self, *, notification_id: UUID, user_id: UUID
    ) -> Notification:
        notification = await self.repository.get_for_user(notification_id, user_id)
        if notification is None:
            raise not_found("Notification")
        return notification

    async def mark_as_read(
        self, *, notification_id: UUID, user_id: UUID
    ) -> Notification:
        notification = await self.repository.get_for_user(
            notification_id, user_id, for_update=True
        )
        if notification is None:
            raise not_found("Notification")
        if notification.status == NotificationStatus.UNREAD:
            notification.status = NotificationStatus.READ
            notification.read_at = utc_now()
            await self.repository.update(notification)
        await self.db.commit()
        await self.db.refresh(notification, attribute_names=["deliveries"])
        return notification

    async def get_unread_count(self, *, user_id: UUID) -> int:
        return await self.repository.count_unread(user_id)

    async def update_delivery_status(
        self,
        *,
        delivery_id: UUID,
        status: NotificationDeliveryStatus,
        failure_reason: str | None = None,
    ) -> NotificationDelivery:
        delivery = await self.repository.get_delivery(delivery_id)
        if delivery is None:
            raise not_found("Notification delivery")
        notification_exists = await self.db.scalar(
            select(Notification.id).where(
                Notification.id == delivery.notification_id,
                Notification.tenant_id == self.tenant_id,
            )
        )
        if notification_exists is None:
            raise not_found("Notification delivery")
        delivery.status = status
        if status == NotificationDeliveryStatus.DELIVERED:
            delivery.delivered_at = utc_now()
            delivery.failure_reason = None
        elif status == NotificationDeliveryStatus.FAILED:
            delivery.failure_reason = (
                failure_reason.strip()
                if failure_reason
                else "Notification delivery failed."
            )
        else:
            delivery.failure_reason = None
        await self.db.flush()
        await self.db.commit()
        await self.db.refresh(delivery)
        return delivery
