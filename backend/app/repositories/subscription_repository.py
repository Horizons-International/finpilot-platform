"""Repository access for subscription records and monthly usage counters."""

from datetime import date
from typing import cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.file import File
from app.models.subscription import Subscription, SubscriptionUsageCounter
from app.models.tenant import Tenant
from app.models.user import User
from app.repositories.tenant_scoped_repository import TenantScopedRepository
from app.utils.enums import UserStatus


class SubscriptionRepository(TenantScopedRepository[Subscription]):
    """Tenant-scoped subscription storage, with explicit admin-only list methods."""

    def __init__(self, db: Session, tenant_id: UUID) -> None:
        super().__init__(db=db, model=Subscription, tenant_id=tenant_id)

    def list_for_tenant(self, *, for_update: bool = False) -> list[Subscription]:
        query = self.query().execution_options(
            skip_tenant_filter=True,
            tenant_scope_reason="load subscription by explicit tenant ID",
        )
        query = query.order_by(Subscription.created_at.desc())
        if for_update:
            query = query.with_for_update()
        return query.all()

    def create_subscription(self, subscription: Subscription) -> Subscription:
        if (
            subscription.tenant_id is not None
            and subscription.tenant_id != self.tenant_id
        ):
            raise ValueError("Subscription tenant does not match repository tenant.")
        subscription.tenant_id = self.tenant_id
        self.db.add(subscription)
        self.db.flush()
        return subscription

    def get_usage_counter(
        self,
        *,
        metric: str,
        period_start: date,
        for_update: bool = False,
    ) -> SubscriptionUsageCounter | None:
        statement = (
            select(SubscriptionUsageCounter)
            .where(
                SubscriptionUsageCounter.tenant_id == self.tenant_id,
                SubscriptionUsageCounter.metric == metric,
                SubscriptionUsageCounter.period_start == period_start,
            )
            .execution_options(
                skip_tenant_filter=True,
                tenant_scope_reason=(
                    "read explicitly tenant-scoped subscription usage counter"
                ),
            )
        )
        if for_update:
            statement = statement.with_for_update()
        return self.db.scalar(statement)

    def list_usage_counters(
        self,
        *,
        period_start: date,
    ) -> list[SubscriptionUsageCounter]:
        statement = (
            select(SubscriptionUsageCounter)
            .where(
                SubscriptionUsageCounter.tenant_id == self.tenant_id,
                SubscriptionUsageCounter.period_start == period_start,
            )
            .execution_options(
                skip_tenant_filter=True,
                tenant_scope_reason="read tenant monthly subscription usage",
            )
        )
        return list(self.db.scalars(statement).all())

    def create_usage_counter(
        self,
        counter: SubscriptionUsageCounter,
    ) -> SubscriptionUsageCounter:
        if counter.tenant_id != self.tenant_id:
            raise ValueError("Usage counter tenant does not match repository tenant.")
        self.db.add(counter)
        self.db.flush()
        return counter

    def count_active_users(self) -> int:
        statement = (
            select(func.count(User.id))
            .where(
                User.tenant_id == self.tenant_id,
                User.status == UserStatus.ACTIVE,
                User.is_deleted.is_(False),
            )
            .execution_options(
                skip_tenant_filter=True,
                tenant_scope_reason="count active users for one subscription tenant",
            )
        )
        return int(cast(int | None, self.db.scalar(statement)) or 0)

    def sum_storage_bytes(self) -> int:
        statement = (
            select(func.coalesce(func.sum(File.file_size), 0))
            .where(File.tenant_id == self.tenant_id)
            .execution_options(
                skip_tenant_filter=True,
                tenant_scope_reason="sum storage bytes for one subscription tenant",
            )
        )
        return int(cast(int | None, self.db.scalar(statement)) or 0)

    @staticmethod
    def list_tenant_for_platform_operation(
        db: Session,
        tenant_id: UUID,
        *,
        for_update: bool = False,
    ) -> list[Subscription]:
        """Load all subscriptions for a platform-admin-selected tenant."""
        statement = (
            select(Subscription)
            .where(Subscription.tenant_id == tenant_id)
            .execution_options(
                skip_tenant_filter=True,
                tenant_scope_reason=(
                    "platform-admin subscription update for explicit tenant ID"
                ),
            )
            .order_by(Subscription.created_at.desc())
        )
        if for_update:
            statement = statement.with_for_update()
        return list(db.scalars(statement).all())

    @staticmethod
    def get_tenant_for_platform_operation(
        db: Session,
        tenant_id: UUID,
        *,
        for_update: bool = False,
    ) -> Tenant | None:
        statement = (
            select(Tenant)
            .where(Tenant.id == tenant_id)
            .execution_options(
                skip_tenant_filter=True,
                tenant_scope_reason=(
                    "platform-admin subscription operation resolves explicit target "
                    "tenant"
                ),
            )
        )
        if for_update:
            statement = statement.with_for_update()
        return db.scalar(statement)

    @staticmethod
    def list_for_platform_admin(
        db: Session,
        *,
        tenant_id: UUID | None = None,
        limit: int = 100,
    ) -> list[Subscription]:
        statement = select(Subscription)
        if tenant_id is not None:
            statement = statement.where(Subscription.tenant_id == tenant_id)
        statement = statement.execution_options(
            skip_tenant_filter=True,
            tenant_scope_reason="platform-admin subscription listing",
        )
        statement = statement.order_by(Subscription.created_at.desc()).limit(limit)
        return list(db.scalars(statement).all())

    @staticmethod
    def get_tenant_for_response(db: Session, tenant_id: UUID) -> Tenant | None:
        statement = (
            select(Tenant)
            .where(Tenant.id == tenant_id)
            .execution_options(
                skip_tenant_filter=True,
                tenant_scope_reason="load organization name for subscription response",
            )
        )
        return db.scalar(statement)
