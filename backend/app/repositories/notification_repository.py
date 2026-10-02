from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from app.models.notification import Notification, NotificationDelivery
from app.repositories.base_repository import BaseRepository
from app.utils.enums import NotificationStatus


class NotificationRepository(
    BaseRepository[Notification],
):
    def __init__(
        self,
        db: Session,
    ) -> None:
        super().__init__(
            db,
            Notification,
        )

    def get_for_user(
        self,
        notification_id: UUID,
        user_id: UUID,
        *,
        for_update: bool = False,
    ) -> Notification | None:
        query = (
            self.db.query(Notification)
            .options(
                selectinload(Notification.deliveries),
            )
            .filter(
                Notification.id == notification_id,
                Notification.user_id == user_id,
            )
        )

        if for_update:
            query = query.with_for_update()

        return query.first()

    def list_for_user(
        self,
        *,
        user_id: UUID,
        status: NotificationStatus | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Notification], int]:
        query = (
            self.db.query(Notification)
            .options(
                selectinload(Notification.deliveries),
            )
            .filter(
                Notification.user_id == user_id,
            )
        )

        if status is not None:
            query = query.filter(
                Notification.status == status,
            )

        total = (
            query.with_entities(
                func.count(Notification.id),
            ).scalar()
            or 0
        )

        offset = (page - 1) * page_size

        notifications = (
            query.order_by(
                Notification.created_at.desc(),
            )
            .offset(offset)
            .limit(page_size)
            .all()
        )

        return notifications, total

    def count_unread(
        self,
        user_id: UUID,
    ) -> int:
        return (
            self.db.query(
                func.count(Notification.id),
            )
            .filter(
                Notification.user_id == user_id,
                Notification.status == NotificationStatus.UNREAD,
            )
            .scalar()
            or 0
        )

    def get_deliveries(
        self,
        notification_id: UUID,
    ) -> list[NotificationDelivery]:
        return (
            self.db.query(NotificationDelivery)
            .filter(
                NotificationDelivery.notification_id == notification_id,
            )
            .order_by(
                NotificationDelivery.created_at,
            )
            .all()
        )
