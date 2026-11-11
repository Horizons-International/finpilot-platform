"""Async quota checks for live subscription capacity gauges."""

from datetime import timedelta
from typing import cast
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.file import File
from app.models.subscription import Subscription
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.subscription import SubscriptionPlan
from app.services.subscription_service import PLAN_CATALOG, _merged_limits
from app.utils.date_time import utc_now
from app.utils.enums import SubscriptionStatus, TenantStatus, UserStatus

_LIMIT_KEY_BY_METRIC = {
    "active_users": "max_users",
    "storage_bytes": "storage_bytes",
}


async def _subscription_rows(
    db: AsyncSession,
    tenant_id: UUID,
    *,
    lock: bool,
) -> list[Subscription]:
    statement = (
        select(Subscription)
        .where(Subscription.tenant_id == tenant_id)
        .order_by(Subscription.created_at.desc())
        .execution_options(
            skip_tenant_filter=True,
            tenant_scope_reason="load subscription by explicit tenant ID",
        )
    )
    if lock:
        statement = statement.with_for_update()
    result = await db.scalars(statement)
    return list(result.all())


async def _get_current_subscription(
    db: AsyncSession,
    tenant_id: UUID,
    *,
    lock: bool,
) -> Subscription:
    rows = await _subscription_rows(db, tenant_id, lock=lock)
    current = next(
        (
            row
            for row in rows
            if row.status in {SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL}
        ),
        None,
    )

    if current is None:
        if rows:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=(
                    "This organization does not have an active "
                    "subscription. Contact the platform owner."
                ),
            )

        tenant_statement = (
            select(Tenant)
            .where(Tenant.id == tenant_id)
            .execution_options(
                skip_tenant_filter=True,
                tenant_scope_reason=(
                    "subscription first-use provisioning resolves explicit tenant"
                ),
            )
        )
        if lock:
            tenant_statement = tenant_statement.with_for_update()
        tenant = await db.scalar(tenant_statement)
        if tenant is None or tenant.status != TenantStatus.ACTIVE:
            raise HTTPException(
                status_code=404, detail="Active organization not found."
            )

        # Re-read after taking the tenant lock, matching the synchronous path's
        # first-use provisioning protection.
        rows = await _subscription_rows(db, tenant_id, lock=lock)
        current = next(
            (
                row
                for row in rows
                if row.status in {SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL}
            ),
            None,
        )
        if current is None and rows:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=(
                    "This organization does not have an active "
                    "subscription. Contact the platform owner."
                ),
            )
        if current is None:
            today = utc_now().date()
            current = Subscription(
                tenant_id=tenant_id,
                plan_name=SubscriptionPlan.STARTER.value,
                status=SubscriptionStatus.TRIAL,
                start_date=today,
                end_date=today + timedelta(days=30),
                usage_limits=_merged_limits(SubscriptionPlan.STARTER.value),
                features=dict(PLAN_CATALOG[SubscriptionPlan.STARTER.value]["features"]),
            )
            db.add(current)
            await db.flush()

    today = utc_now().date()
    if current.end_date < today:
        current.status = SubscriptionStatus.EXPIRED
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=(
                "The subscription has expired. Contact the platform owner to renew it."
            ),
        )
    if current.start_date > today:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=(
                "The subscription does not start until "
                f"{current.start_date.isoformat()}."
            ),
        )
    if current.status not in {SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL}:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="The subscription is not active. Contact the platform owner.",
        )
    return current


async def ensure_subscription_capacity(
    db: AsyncSession,
    tenant_id: UUID,
    metric: str,
    *,
    additional: int = 0,
) -> int:
    """Check active-user or storage capacity using an async SQLAlchemy session."""
    if metric not in {"active_users", "storage_bytes"}:
        raise ValueError("Capacity checks support active_users and storage_bytes only.")
    if additional < 0:
        raise ValueError("Additional capacity must be zero or greater.")

    current = await _get_current_subscription(db, tenant_id, lock=True)

    if metric == "active_users":
        statement = (
            select(func.count(User.id))
            .where(
                User.tenant_id == tenant_id,
                User.status == UserStatus.ACTIVE,
                User.is_deleted.is_(False),
            )
            .execution_options(
                skip_tenant_filter=True,
                tenant_scope_reason="count active users for one subscription tenant",
            )
        )
        used = int(cast(int | None, await db.scalar(statement)) or 0)
        unit = "active users"
    else:
        statement = (
            select(func.coalesce(func.sum(File.file_size), 0))
            .where(File.tenant_id == tenant_id)
            .execution_options(
                skip_tenant_filter=True,
                tenant_scope_reason="sum storage bytes for one subscription tenant",
            )
        )
        used = int(cast(int | None, await db.scalar(statement)) or 0)
        unit = "bytes of storage"

    limit_value = current.usage_limits.get(_LIMIT_KEY_BY_METRIC[metric])
    if limit_value is not None and used + additional > limit_value:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Subscription limit reached for {unit} ({limit_value}). "
                "Remove usage or ask the platform owner to change the limit."
            ),
            headers={
                "X-Subscription-Metric": metric,
                "X-Subscription-Limit": str(limit_value),
            },
        )
    return used
