from typing import cast
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from app.models.notification import Notification, NotificationDelivery
from app.models.user import User
from app.repositories.tenant_scoped_repository import TenantScopedRepository
from app.utils.enums import NotificationStatus


class NotificationRepository(TenantScopedRepository[Notification]):
    def __init__(self, db: Session, tenant_id: UUID | None = None) -> None:
        resolved_tenant_id = (
            tenant_id if tenant_id is not None else db.info.get("tenant_id")
        )
        if not isinstance(resolved_tenant_id, UUID):
            raise ValueError("A tenant context is required for notifications.")
        super().__init__(db=db, model=Notification, tenant_id=resolved_tenant_id)

    def _ensure_user_belongs_to_tenant(self, user_id: UUID) -> None:
        user_exists = (
            self.db.query(User.id)
            .filter(User.id == user_id, User.tenant_id == self.tenant_id)
            .first()
        )
        if user_exists is None:
            raise ValueError(
                "The notification recipient does not belong to the current tenant."
            )

    def create(self, notification: Notification) -> Notification:
        self._ensure_user_belongs_to_tenant(notification.user_id)
        return super().create(notification)

    def update(self, notification: Notification) -> Notification:
        self._ensure_user_belongs_to_tenant(notification.user_id)
        return super().update(notification)

    def _notification_query(self):
        return self.query().options(selectinload(Notification.deliveries))

    def get_for_user(
        self,
        notification_id: UUID,
        user_id: UUID,
        *,
        for_update: bool = False,
    ) -> Notification | None:

        self._ensure_user_belongs_to_tenant(user_id)

        query = self._notification_query().filter(
            Notification.id == notification_id,
            Notification.user_id == user_id,
        )

        if for_update:
            query = query.with_for_update()

        return cast(Notification | None, query.first())

    def list_for_user(
        self,
        *,
        user_id: UUID,
        status: NotificationStatus | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Notification], int]:
        self._ensure_user_belongs_to_tenant(user_id)
        query = self._notification_query().filter(Notification.user_id == user_id)
        if status is not None:
            query = query.filter(Notification.status == status)

        total = query.with_entities(func.count(Notification.id)).scalar() or 0
        offset = (page - 1) * page_size
        notifications = (
            query.order_by(Notification.created_at.desc())
            .offset(offset)
            .limit(page_size)
            .all()
        )
        return notifications, int(total)

    def count_unread(self, user_id: UUID) -> int:
        self._ensure_user_belongs_to_tenant(user_id)
        count = (
            self.query()
            .with_entities(func.count(Notification.id))
            .filter(
                Notification.user_id == user_id,
                Notification.status == NotificationStatus.UNREAD,
            )
            .scalar()
        )
        return int(count or 0)

    def get_deliveries(self, notification_id: UUID) -> list[NotificationDelivery]:
        notification_exists = (
            self.query().filter(Notification.id == notification_id).first()
        )
        if notification_exists is None:
            return []
        return (
            self.db.query(NotificationDelivery)
            .filter(
                NotificationDelivery.tenant_id == self.tenant_id,
                NotificationDelivery.notification_id == notification_id,
            )
            .order_by(NotificationDelivery.created_at)
            .all()
        )
