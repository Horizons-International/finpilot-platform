"""Native-async platform subscription administration and metering."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, timedelta
from typing import Any, cast
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.file import File
from app.models.subscription import Subscription, SubscriptionUsageCounter
from app.models.tenant import Tenant
from app.models.user import User
from app.services.async_subscription_capacity import _get_current_subscription
from app.services.subscription_service import (
    _LIMIT_KEY_BY_METRIC,
    PLAN_CATALOG,
    _merged_limits,
    _period_end,
    _period_start,
    is_billing_exempt_path,
)
from app.utils.date_time import utc_now
from app.utils.enums import SubscriptionStatus, TenantStatus, UserStatus


class AsyncSubscriptionService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @staticmethod
    def plans() -> list[dict[str, Any]]:
        return [
            {
                "plan_name": name,
                "usage_limits": dict(values["usage_limits"]),
                "features": dict(values["features"]),
            }
            for name, values in PLAN_CATALOG.items()
        ]

    @staticmethod
    def _target(statement):
        return statement.execution_options(
            skip_tenant_filter=True,
            tenant_scope_reason="platform-admin operation targets an explicit tenant",
        )

    @contextmanager
    def _tenant_scope(self, tenant_id: UUID):
        previous = self.db.info.get("tenant_id")
        self.db.info["tenant_id"] = tenant_id
        try:
            yield
        finally:
            if previous is None:
                self.db.info.pop("tenant_id", None)
            else:
                self.db.info["tenant_id"] = previous

    async def _rows(self, tenant_id: UUID, *, lock: bool = False) -> list[Subscription]:
        statement = self._target(
            select(Subscription)
            .where(Subscription.tenant_id == tenant_id)
            .order_by(Subscription.created_at.desc())
        )
        if lock:
            statement = statement.with_for_update()
        rows = await self.db.scalars(statement)
        return list(rows.all())

    async def _tenant(self, tenant_id: UUID) -> Tenant:
        tenant = cast(
            Tenant | None,
            await self.db.scalar(
                self._target(
                    select(Tenant).where(Tenant.id == tenant_id).with_for_update()
                )
            ),
        )

        if tenant is None or tenant.status != TenantStatus.ACTIVE:
            raise HTTPException(
                status_code=404,
                detail="Active organization not found.",
            )

        return tenant

    async def create(
        self,
        *,
        tenant_id: UUID,
        plan_name: str,
        start_date: date | None = None,
        end_date: date | None = None,
        status_value: SubscriptionStatus = SubscriptionStatus.ACTIVE,
        usage_limits: dict[str, int | None] | None = None,
    ) -> Subscription:
        await self._tenant(tenant_id)
        if plan_name not in PLAN_CATALOG:
            raise HTTPException(status_code=422, detail="Unknown subscription plan.")
        with self._tenant_scope(tenant_id):
            try:
                rows = await self._rows(tenant_id, lock=True)
                today = utc_now().date()
                for row in rows:
                    if (
                        row.status
                        in {SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL}
                        and row.end_date < today
                    ):
                        row.status = SubscriptionStatus.EXPIRED
                if any(
                    row.status in {SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL}
                    and row.end_date >= today
                    for row in rows
                ):
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            "This organization already has a current "
                            "subscription. Update it instead."
                        ),
                    )
                start = start_date or today
                end = end_date or start + timedelta(days=365)
                if end < start:
                    raise HTTPException(
                        status_code=422,
                        detail="end_date must be on or after start_date.",
                    )
                if (
                    status_value
                    in {SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL}
                    and end < today
                ):
                    raise HTTPException(
                        status_code=422,
                        detail="An active subscription cannot already be expired.",
                    )
                item = Subscription(
                    tenant_id=tenant_id,
                    plan_name=plan_name,
                    status=status_value,
                    start_date=start,
                    end_date=end,
                    usage_limits=_merged_limits(plan_name, usage_limits),
                    features=dict(PLAN_CATALOG[plan_name]["features"]),
                )
                self.db.add(item)
                await self.db.commit()
                await self.db.refresh(item)
                return item
            except Exception:
                await self.db.rollback()
                raise

    async def get_latest(self, tenant_id: UUID) -> Subscription:
        rows = await self._rows(tenant_id)
        if not rows:
            raise HTTPException(status_code=404, detail="Subscription not found.")
        item = rows[0]
        if (
            item.status in {SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL}
            and item.end_date < utc_now().date()
        ):
            with self._tenant_scope(tenant_id):
                try:
                    item.status = SubscriptionStatus.EXPIRED
                    await self.db.commit()
                    await self.db.refresh(item)
                except Exception:
                    await self.db.rollback()
                    raise
        return item

    async def list_subscriptions(
        self, *, tenant_id: UUID | None = None, limit: int = 100
    ) -> list[Subscription]:
        statement = (
            select(Subscription).order_by(Subscription.created_at.desc()).limit(limit)
        )
        if tenant_id is not None:
            statement = statement.where(Subscription.tenant_id == tenant_id)
        rows = await self.db.scalars(self._target(statement))
        return list(rows.all())

    async def update(self, tenant_id: UUID, changes: dict[str, Any]) -> Subscription:
        rows = await self._rows(tenant_id, lock=True)
        if not rows:
            raise HTTPException(status_code=404, detail="Subscription not found.")
        with self._tenant_scope(tenant_id):
            try:
                item = next(
                    (
                        row
                        for row in rows
                        if row.status
                        in {SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL}
                    ),
                    rows[0],
                )
                next_plan = str(changes.get("plan_name") or item.plan_name)
                if next_plan not in PLAN_CATALOG:
                    raise HTTPException(
                        status_code=422, detail="Unknown subscription plan."
                    )
                custom_limits = changes.get("usage_limits")
                if changes.get("plan_name") is not None:
                    item.plan_name = next_plan
                    item.usage_limits = _merged_limits(next_plan, custom_limits)
                    item.features = dict(PLAN_CATALOG[next_plan]["features"])
                elif custom_limits is not None:
                    item.usage_limits = _merged_limits(next_plan, custom_limits)
                for field in ("start_date", "end_date", "status"):
                    if field in changes and changes[field] is not None:
                        setattr(item, field, changes[field])
                if item.end_date < item.start_date:
                    raise HTTPException(
                        status_code=422,
                        detail="end_date must be on or after start_date.",
                    )
                if (
                    item.status in {SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL}
                    and item.end_date < utc_now().date()
                ):
                    raise HTTPException(
                        status_code=422,
                        detail="An active subscription cannot already be expired.",
                    )
                await self.db.commit()
                await self.db.refresh(item)
                return item
            except Exception:
                await self.db.rollback()
                raise

    async def cancel(self, tenant_id: UUID) -> Subscription:
        return await self.update(tenant_id, {"status": SubscriptionStatus.CANCELLED})

    async def serialize(self, item: Subscription) -> dict[str, Any]:
        tenant = await self.db.scalar(
            self._target(select(Tenant).where(Tenant.id == item.tenant_id))
        )
        if tenant is None:
            raise HTTPException(status_code=404, detail="Organization not found.")
        return {
            "id": item.id,
            "tenant_id": item.tenant_id,
            "organization_name": tenant.name,
            "plan_name": item.plan_name,
            "status": item.status,
            "start_date": item.start_date,
            "end_date": item.end_date,
            "usage_limits": dict(item.usage_limits or {}),
            "features": dict(item.features or {}),
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }

    async def get_usage(self, tenant_id: UUID) -> dict[str, Any]:
        rows = await self._rows(tenant_id)
        today = utc_now().date()
        subscription = next(
            (
                row
                for row in rows
                if row.status in {SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL}
                and row.end_date >= today
            ),
            None,
        )
        if subscription is None:
            if rows:
                subscription = rows[0]
                if (
                    subscription.status
                    in {SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL}
                    and subscription.end_date < today
                ):
                    with self._tenant_scope(tenant_id):
                        try:
                            subscription.status = SubscriptionStatus.EXPIRED
                            await self.db.commit()
                        except Exception:
                            await self.db.rollback()
                            raise
            else:
                raise HTTPException(status_code=404, detail="Subscription not found.")
        period = _period_start()
        counter_rows = await self.db.scalars(
            self._target(
                select(SubscriptionUsageCounter).where(
                    SubscriptionUsageCounter.tenant_id == tenant_id,
                    SubscriptionUsageCounter.period_start == period,
                )
            )
        )
        used = {row.metric: row.used for row in counter_rows.all()}
        active = int(
            await self.db.scalar(
                self._target(
                    select(func.count(User.id)).where(
                        User.tenant_id == tenant_id,
                        User.status == UserStatus.ACTIVE,
                        User.is_deleted.is_(False),
                    )
                )
            )
            or 0
        )
        storage = int(
            await self.db.scalar(
                self._target(
                    select(func.coalesce(func.sum(File.file_size), 0)).where(
                        File.tenant_id == tenant_id
                    )
                )
            )
            or 0
        )
        current = {
            "api_calls": (used.get("api_calls", 0), "calls"),
            "verification_checks": (used.get("verification_checks", 0), "checks"),
            "ai_requests": (used.get("ai_requests", 0), "requests"),
            "transactions": (used.get("transactions", 0), "transactions"),
            "active_users": (active, "users"),
            "storage_bytes": (storage, "bytes"),
        }
        metrics = []
        for name, (count, unit) in current.items():
            limit = (subscription.usage_limits or {}).get(_LIMIT_KEY_BY_METRIC[name])
            metrics.append(
                {
                    "metric": name,
                    "used": count,
                    "limit": limit,
                    "remaining": None if limit is None else max(limit - count, 0),
                    "unit": unit,
                }
            )
        return {
            "tenant_id": tenant_id,
            "subscription_id": subscription.id,
            "plan_name": subscription.plan_name,
            "status": subscription.status,
            "period_start": period,
            "period_end": _period_end(period),
            "metrics": metrics,
        }


async def record_subscription_usage(
    db: AsyncSession, tenant_id: UUID, metric: str, amount: int = 1
) -> SubscriptionUsageCounter:
    if metric not in _LIMIT_KEY_BY_METRIC or amount <= 0:
        raise ValueError("Invalid subscription usage metric or amount.")
    subscription = await _get_current_subscription(db, tenant_id, lock=True)
    period = _period_start()
    stmt = (
        select(SubscriptionUsageCounter)
        .where(
            SubscriptionUsageCounter.tenant_id == tenant_id,
            SubscriptionUsageCounter.metric == metric,
            SubscriptionUsageCounter.period_start == period,
        )
        .with_for_update()
    )
    counter = await db.scalar(stmt)
    if counter is None:
        counter = SubscriptionUsageCounter(
            tenant_id=tenant_id, metric=metric, period_start=period, used=0
        )
        db.add(counter)
        await db.flush()
    limit = (subscription.usage_limits or {}).get(_LIMIT_KEY_BY_METRIC[metric])
    if limit is not None and counter.used + amount > limit:
        await db.rollback()
        raise HTTPException(
            status_code=429,
            detail=f"Subscription limit reached for '{metric}' ({limit} per month).",
            headers={
                "X-Subscription-Metric": metric,
                "X-Subscription-Limit": str(limit),
            },
        )
    counter.used += amount
    await db.commit()
    await db.refresh(counter)
    return counter


__all__ = [
    "AsyncSubscriptionService",
    "record_subscription_usage",
    "is_billing_exempt_path",
]
