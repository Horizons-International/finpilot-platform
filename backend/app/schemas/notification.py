from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.utils.enums import (
    NotificationChannel,
    NotificationDeliveryStatus,
    NotificationStatus,
)


class NotificationDeliveryResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: UUID
    notification_id: UUID
    channel: NotificationChannel
    status: NotificationDeliveryStatus
    delivered_at: datetime | None
    failure_reason: str | None
    created_at: datetime
    updated_at: datetime


class NotificationResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: UUID
    user_id: UUID
    title: str
    message: str
    status: NotificationStatus
    event_type: str
    resource_type: str | None
    resource_id: UUID | None
    read_at: datetime | None
    created_at: datetime
    updated_at: datetime
    deliveries: list[NotificationDeliveryResponse]


class NotificationListResponse(BaseModel):
    notifications: list[NotificationResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class NotificationUnreadCountResponse(BaseModel):
    unread_count: int
