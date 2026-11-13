"""Tenant-scoped asynchronous notification persistence."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.notification import Notification, NotificationDelivery
from app.models.user import User
from app.repositories.async_tenant_scoped_repository import (
    AsyncTenantScopedRepository,
)
from app.utils.enums import NotificationStatus


class AsyncNotificationRepository(AsyncTenantScopedRepository[Notification]):
    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        super().__init__(db, Notification, tenant_id)

    async def ensure_recipient(self, user_id: UUID) -> User | None:
        return await self.db.scalar(
            select(User).where(
                User.id == user_id,
                User.tenant_id == self.tenant_id,
            )
        )

    async def validate_recipient(self, user_id: UUID) -> None:
        if await self.ensure_recipient(user_id) is None:
            raise ValueError(
                "The notification recipient does not belong to the current tenant."
            )

    async def get_for_user(
        self,
        notification_id: UUID,
        user_id: UUID,
        *,
        for_update: bool = False,
    ) -> Notification | None:
        await self.validate_recipient(user_id)
        statement = (
            self.query()
            .where(
                Notification.id == notification_id,
                Notification.user_id == user_id,
            )
            .options(selectinload(Notification.deliveries))
        )
        if for_update:
            statement = statement.with_for_update()
        return await self.db.scalar(statement)

    async def list_for_user(
        self,
        *,
        user_id: UUID,
        status: NotificationStatus | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Notification], int]:
        await self.validate_recipient(user_id)
        filters = [
            Notification.tenant_id == self.tenant_id,
            Notification.user_id == user_id,
        ]
        if status is not None:
            filters.append(Notification.status == status)
        total = int(
            await self.db.scalar(select(func.count(Notification.id)).where(*filters))
            or 0
        )
        statement = (
            select(Notification)
            .where(*filters)
            .options(selectinload(Notification.deliveries))
            .order_by(Notification.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = await self.db.scalars(statement)
        return list(rows.all()), total

    async def count_unread(self, user_id: UUID) -> int:
        await self.validate_recipient(user_id)
        return int(
            await self.db.scalar(
                select(func.count(Notification.id)).where(
                    Notification.tenant_id == self.tenant_id,
                    Notification.user_id == user_id,
                    Notification.status == NotificationStatus.UNREAD,
                )
            )
            or 0
        )

    async def get_delivery(self, delivery_id: UUID) -> NotificationDelivery | None:
        return await self.db.scalar(
            select(NotificationDelivery).where(
                NotificationDelivery.id == delivery_id,
                NotificationDelivery.tenant_id == self.tenant_id,
            )
        )
