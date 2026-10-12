from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.notification import Notification, NotificationDelivery
from app.models.user import User
from app.repositories.notification_repository import NotificationRepository
from app.schemas.notification import NotificationListResponse, NotificationResponse
from app.services.audit_service import AuditService
from app.services.tenant_context import resolve_tenant_context
from app.utils.date_time import utc_now
from app.utils.enums import (
    NotificationChannel,
    NotificationDeliveryStatus,
    NotificationEventType,
    NotificationStatus,
)
from app.utils.errors import bad_request, not_found
from app.utils.pagination import validate_pagination


class NotificationService:
    def __init__(self, db: Session, tenant_id: UUID | None = None) -> None:
        self.db = db
        self._requested_tenant_id = tenant_id
        self.tenant_id: UUID | None = tenant_id
        self.repository: NotificationRepository | None = None
        self.audit_service = AuditService(db)

    def _repository(self) -> NotificationRepository:
        if self.repository is None:
            self.tenant_id = resolve_tenant_context(
                self.db, self._requested_tenant_id, resource_name="notifications"
            )
            self.repository = NotificationRepository(self.db, tenant_id=self.tenant_id)
        return self.repository

    def create_notification(
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
        tenant_id = resolve_tenant_context(
            self.db, self._requested_tenant_id, resource_name="notifications"
        )
        self.tenant_id = tenant_id
        user = (
            self.db.query(User)
            .filter(User.id == user_id, User.tenant_id == tenant_id)
            .first()
        )
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
            tenant_id=tenant_id,
            user_id=user_id,
            title=normalized_title,
            message=normalized_message,
            status=NotificationStatus.UNREAD,
            event_type=event_type.value,
            resource_type=resource_type,
            resource_id=resource_id,
        )
        # Repository verifies recipient ownership, assigns tenant_id and flushes.
        notification = self._repository().create(notification)

        for channel in dict.fromkeys(channels):
            delivery_status = NotificationDeliveryStatus.PENDING
            delivered_at: datetime | None = None
            if channel == NotificationChannel.IN_APP:
                delivery_status = NotificationDeliveryStatus.DELIVERED
                delivered_at = utc_now()
            delivery = NotificationDelivery(
                tenant_id=tenant_id,
                notification_id=notification.id,
                channel=channel,
                status=delivery_status,
                delivered_at=delivered_at,
            )
            self.db.add(delivery)
        self.db.flush()
        return notification

    def list_notifications(
        self,
        *,
        user_id: UUID,
        status: NotificationStatus | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> NotificationListResponse:
        validate_pagination(page, page_size)
        notifications, total = self._repository().list_for_user(
            user_id=user_id, status=status, page=page, page_size=page_size
        )
        total_pages = (total + page_size - 1) // page_size if total > 0 else 0
        return NotificationListResponse(
            notifications=[
                NotificationResponse.model_validate(item) for item in notifications
            ],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )

    def get_notification(self, *, notification_id: UUID, user_id: UUID) -> Notification:
        notification = self._repository().get_for_user(notification_id, user_id)
        if notification is None:
            raise not_found("Notification")
        return notification

    def mark_as_read(self, *, notification_id: UUID, user_id: UUID) -> Notification:
        notification = self._repository().get_for_user(
            notification_id, user_id, for_update=True
        )
        if notification is None:
            raise not_found("Notification")
        if notification.status == NotificationStatus.UNREAD:
            notification.status = NotificationStatus.READ
            notification.read_at = utc_now()
            self._repository().update(notification)
        self.db.commit()
        self.db.refresh(notification)
        return notification

    def get_unread_count(self, *, user_id: UUID) -> int:
        return self._repository().count_unread(user_id)

    def update_delivery_status(
        self,
        *,
        delivery_id: UUID,
        status: NotificationDeliveryStatus,
        failure_reason: str | None = None,
    ) -> NotificationDelivery:
        tenant_id = resolve_tenant_context(
            self.db, self._requested_tenant_id, resource_name="notification deliveries"
        )
        self.tenant_id = tenant_id
        delivery = (
            self.db.query(NotificationDelivery)
            .filter(
                NotificationDelivery.id == delivery_id,
                NotificationDelivery.tenant_id == tenant_id,
            )
            .first()
        )
        if delivery is None:
            raise not_found("Notification delivery")
        notification_exists = (
            self.db.query(Notification.id)
            .filter(
                Notification.id == delivery.notification_id,
                Notification.tenant_id == tenant_id,
            )
            .first()
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
        self.db.flush()
        self.db.commit()
        self.db.refresh(delivery)
        return delivery
