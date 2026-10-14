"""Subscription management, metering, and quota enforcement."""

from calendar import monthrange
from datetime import date, timedelta
from typing import Any, cast
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.file import File
from app.models.subscription import Subscription, SubscriptionUsageCounter
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.subscription import SubscriptionPlan, SubscriptionUsageMetric
from app.utils.date_time import utc_now
from app.utils.enums import SubscriptionStatus, TenantStatus, UserStatus

# Conservative defaults keep Starter bounded while allowing existing test and
# development tenants to use normal workflows. These are product defaults, not
# prices; no payment processor is implied by this foundation.
PLAN_CATALOG: dict[str, dict[str, Any]] = {
    SubscriptionPlan.STARTER.value: {
        "usage_limits": {
            "max_users": 100,
            "api_calls": 50_000,
            "verification_checks": 1_000,
            "ai_requests": 500,
            "transactions": 1_000,
            "storage_bytes": 1_073_741_824,
        },
        "features": {
            "advanced_reporting": False,
            "dedicated_integrations": False,
        },
    },
    SubscriptionPlan.PROFESSIONAL.value: {
        "usage_limits": {
            "max_users": 1_000,
            "api_calls": 1_000_000,
            "verification_checks": 100_000,
            "ai_requests": 25_000,
            "transactions": 100_000,
            "storage_bytes": 107_374_182_400,
        },
        "features": {
            "advanced_reporting": True,
            "dedicated_integrations": False,
        },
    },
    SubscriptionPlan.ENTERPRISE.value: {
        "usage_limits": {
            "max_users": None,
            "api_calls": None,
            "verification_checks": None,
            "ai_requests": None,
            "transactions": None,
            "storage_bytes": None,
        },
        "features": {
            "advanced_reporting": True,
            "dedicated_integrations": True,
        },
    },
}

_ALLOWED_LIMIT_KEYS = frozenset(
    {
        "max_users",
        "api_calls",
        "verification_checks",
        "ai_requests",
        "transactions",
        "storage_bytes",
    }
)
_COUNTED_METRICS = frozenset(
    {"api_calls", "verification_checks", "ai_requests", "transactions"}
)
_LIMIT_KEY_BY_METRIC = {
    "active_users": "max_users",
    "storage_bytes": "storage_bytes",
    "api_calls": "api_calls",
    "verification_checks": "verification_checks",
    "ai_requests": "ai_requests",
    "transactions": "transactions",
}
_BILLING_EXEMPT_PREFIXES = (
    "/api/v1/subscriptions",
    "/api/v1/auth",
    "/api/v1/partner-onboarding",
    "/api/v1/health",
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
)


def is_billing_exempt_path(path: str) -> bool:
    """Allow authentication and billing-management routes during quota blocks."""
    return any(
        path == prefix or path.startswith(prefix + "/")
        for prefix in _BILLING_EXEMPT_PREFIXES
    )


def _period_start(today: date | None = None) -> date:
    current = today or utc_now().date()
    return current.replace(day=1)


def _period_end(period_start: date) -> date:
    return date(
        period_start.year,
        period_start.month,
        monthrange(period_start.year, period_start.month)[1],
    )


def _merged_limits(
    plan_name: str, custom: dict[str, int | None] | None = None
) -> dict[str, int | None]:
    if plan_name not in PLAN_CATALOG:
        raise HTTPException(status_code=422, detail="Unknown subscription plan.")
    limits = dict(PLAN_CATALOG[plan_name]["usage_limits"])
    if custom:
        unknown_keys = set(custom) - _ALLOWED_LIMIT_KEYS
        if unknown_keys:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Unsupported usage limit(s): {', '.join(sorted(unknown_keys))}.",
                ),
            )
        for key, value in custom.items():
            if value is not None and value < 0:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"Usage limit '{key}' must be zero"
                        " or greater, or null for unlimited.",
                    ),
                )
            limits[key] = value
    return limits


def _tenant_statement(statement: Any, reason: str) -> Any:
    return statement.execution_options(
        skip_tenant_filter=True,
        tenant_scope_reason=reason,
    )


def _subscription_rows(
    db: Session, tenant_id: UUID, *, lock: bool = False
) -> list[Subscription]:
    statement = select(Subscription).where(Subscription.tenant_id == tenant_id)
    statement = _tenant_statement(statement, "load subscription by explicit tenant ID")
    if lock:
        statement = statement.with_for_update()
    return cast(
        list[Subscription],
        list(db.scalars(statement.order_by(Subscription.created_at.desc())).all()),
    )


def _get_current_subscription(
    db: Session,
    tenant_id: UUID,
    *,
    create_trial_if_missing: bool = True,
    lock: bool = False,
) -> Subscription:
    rows = _subscription_rows(db, tenant_id, lock=lock)
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
                    "subscription. Contact the platform owner.",
                ),
            )
        if not create_trial_if_missing:
            raise HTTPException(status_code=404, detail="Subscription not found.")

        tenant_statement = select(Tenant).where(Tenant.id == tenant_id)
        tenant = cast(
            Tenant | None,
            db.scalar(
                _tenant_statement(
                    tenant_statement,
                    "verify tenant before trial subscription provisioning",
                ).with_for_update()
            ),
        )
        if tenant is None or tenant.status != TenantStatus.ACTIVE:
            raise HTTPException(
                status_code=404, detail="Active organization not found."
            )

        # The organization lock serializes first-use provisioning when no
        # subscription row exists yet. Re-read after obtaining that lock.
        rows = _subscription_rows(db, tenant_id, lock=lock)
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
                    "subscription. Contact the platform owner.",
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
            db.flush()

    today = utc_now().date()
    if current.end_date < today:
        current.status = SubscriptionStatus.EXPIRED
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=(
                "The subscription has expired. Contact the platform owner to renew it.",
            ),
        )
    if current.start_date > today:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=(
                "The subscription does not start until "
                f"{current.start_date.isoformat()}.",
            ),
        )
    if current.status not in {SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL}:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="The subscription is not active. Contact the platform owner.",
        )
    return current


def record_subscription_usage(
    db: Session,
    tenant_id: UUID,
    metric: str,
    amount: int = 1,
) -> SubscriptionUsageCounter:
    """Atomically consume a monthly allowance, raising HTTP 429 at the limit."""
    if metric not in _COUNTED_METRICS:
        raise ValueError(f"'{metric}' is not a countable subscription metric.")
    if amount <= 0:
        raise ValueError("Usage amount must be greater than zero.")

    subscription = _get_current_subscription(db, tenant_id, lock=True)
    period_start = _period_start()
    statement = select(SubscriptionUsageCounter).where(
        SubscriptionUsageCounter.tenant_id == tenant_id,
        SubscriptionUsageCounter.metric == metric,
        SubscriptionUsageCounter.period_start == period_start,
    )
    counter = cast(
        SubscriptionUsageCounter | None,
        db.scalar(
            _tenant_statement(
                statement,
                "read the explicitly tenant-scoped monthly usage counter",
            ).with_for_update()
        ),
    )
    if counter is None:
        counter = SubscriptionUsageCounter(
            tenant_id=tenant_id,
            metric=metric,
            period_start=period_start,
            used=0,
        )
        db.add(counter)
        db.flush()

    limit_key = _LIMIT_KEY_BY_METRIC[metric]
    limit_value = subscription.usage_limits.get(limit_key)
    if limit_value is not None and counter.used + amount > limit_value:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Subscription limit reached for '{metric}' ({limit_value} per month). "
                "Upgrade the plan or ask the platform owner to change the limit."
            ),
            headers={
                "X-Subscription-Metric": metric,
                "X-Subscription-Limit": str(limit_value),
            },
        )

    counter.used += amount
    db.commit()
    db.refresh(counter)
    return counter


def ensure_subscription_capacity(
    db: Session,
    tenant_id: UUID,
    metric: str,
    *,
    additional: int = 0,
) -> int:
    """Check live user/storage gauges before creating the requested resource."""
    if metric not in {"active_users", "storage_bytes"}:
        raise ValueError("Capacity checks support active_users and storage_bytes only.")
    if additional < 0:
        raise ValueError("Additional capacity must be zero or greater.")

    subscription = _get_current_subscription(db, tenant_id, lock=True)
    if metric == "active_users":
        query = select(func.count(User.id)).where(
            User.tenant_id == tenant_id,
            User.status == UserStatus.ACTIVE,
            User.is_deleted.is_(False),
        )
        raw_used = db.scalar(
            _tenant_statement(query, "count active users for one subscription tenant")
        )
        used = int(cast(int | None, raw_used) or 0)
        unit = "active users"
    else:
        query = select(func.coalesce(func.sum(File.file_size), 0)).where(
            File.tenant_id == tenant_id
        )
        raw_used = db.scalar(
            _tenant_statement(query, "sum storage bytes for one subscription tenant")
        )
        used = int(cast(int | None, raw_used) or 0)
        unit = "bytes of storage"

    limit_value = subscription.usage_limits.get(_LIMIT_KEY_BY_METRIC[metric])
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


class SubscriptionService:
    """Platform-admin operations and tenant usage reporting."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        *,
        tenant_id: UUID,
        plan_name: str,
        start_date: date | None = None,
        end_date: date | None = None,
        status_value: SubscriptionStatus = SubscriptionStatus.ACTIVE,
        usage_limits: dict[str, int | None] | None = None,
    ) -> Subscription:
        tenant_statement = select(Tenant).where(Tenant.id == tenant_id)
        tenant = cast(
            Tenant | None,
            self.db.scalar(
                _tenant_statement(
                    tenant_statement, "platform-admin subscription creation target"
                ).with_for_update()
            ),
        )
        if tenant is None:
            raise HTTPException(status_code=404, detail="Organization not found.")
        # Platform administrators intentionally operate across tenants; after
        # resolving the authorized target, align regular ORM refreshes with it.
        self.db.info["tenant_id"] = tenant_id
        if plan_name not in PLAN_CATALOG:
            raise HTTPException(status_code=422, detail="Unknown subscription plan.")

        # Serialize current-subscription changes for the target tenant.
        existing = _subscription_rows(self.db, tenant_id, lock=True)
        today = utc_now().date()
        expired_rows_changed = False
        for row in existing:
            if (
                row.status in {SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL}
                and row.end_date < today
            ):
                row.status = SubscriptionStatus.EXPIRED
                expired_rows_changed = True
        if expired_rows_changed:
            self.db.commit()
            existing = _subscription_rows(self.db, tenant_id, lock=True)
        if any(
            row.status in {SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL}
            and row.end_date >= today
            for row in existing
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "This organization already has a "
                    "current subscription. Update it instead.",
                ),
            )

        today = utc_now().date()
        selected_start = start_date or today
        selected_end = end_date or selected_start + timedelta(days=365)
        if selected_end < selected_start:
            raise HTTPException(
                status_code=422, detail="end_date must be on or after start_date."
            )
        subscription = Subscription(
            tenant_id=tenant_id,
            plan_name=plan_name,
            status=status_value,
            start_date=selected_start,
            end_date=selected_end,
            usage_limits=_merged_limits(plan_name, usage_limits),
            features=dict(PLAN_CATALOG[plan_name]["features"]),
        )
        if status_value in {SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL}:
            today = utc_now().date()
            if selected_end < today:
                raise HTTPException(
                    status_code=422,
                    detail="An active subscription cannot already be expired.",
                )
        self.db.add(subscription)
        self.db.commit()
        self.db.refresh(subscription)
        return subscription

    def get_latest(self, tenant_id: UUID) -> Subscription:
        self.db.info["tenant_id"] = tenant_id
        rows = _subscription_rows(self.db, tenant_id)
        if not rows:
            raise HTTPException(status_code=404, detail="Subscription not found.")
        latest = rows[0]
        if (
            latest.status in {SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL}
            and latest.end_date < utc_now().date()
        ):
            latest.status = SubscriptionStatus.EXPIRED
            self.db.commit()
            self.db.refresh(latest)
        return latest

    def list_subscriptions(
        self, *, tenant_id: UUID | None = None, limit: int = 100
    ) -> list[Subscription]:
        statement = select(Subscription)
        if tenant_id is not None:
            statement = statement.where(Subscription.tenant_id == tenant_id)
        statement = _tenant_statement(statement, "platform-admin subscription listing")
        return cast(
            list[Subscription],
            list(
                self.db.scalars(
                    statement.order_by(Subscription.created_at.desc()).limit(limit)
                ).all()
            ),
        )

    def update(self, tenant_id: UUID, changes: dict[str, Any]) -> Subscription:
        rows = _subscription_rows(self.db, tenant_id, lock=True)
        if not rows:
            raise HTTPException(status_code=404, detail="Subscription not found.")
        self.db.info["tenant_id"] = tenant_id
        subscription = next(
            (
                row
                for row in rows
                if row.status in {SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL}
            ),
            rows[0],
        )
        plan_changed = "plan_name" in changes and changes["plan_name"] is not None
        next_plan = str(changes.get("plan_name") or subscription.plan_name)
        if next_plan not in PLAN_CATALOG:
            raise HTTPException(status_code=422, detail="Unknown subscription plan.")

        custom_limits = changes.get("usage_limits")
        if plan_changed:
            subscription.usage_limits = _merged_limits(next_plan, custom_limits)
            subscription.features = dict(PLAN_CATALOG[next_plan]["features"])
            subscription.plan_name = next_plan
        elif custom_limits is not None:
            subscription.usage_limits = _merged_limits(next_plan, custom_limits)

        for field in ("start_date", "end_date", "status"):
            if field in changes and changes[field] is not None:
                setattr(subscription, field, changes[field])
        if subscription.end_date < subscription.start_date:
            raise HTTPException(
                status_code=422, detail="end_date must be on or after start_date."
            )
        if (
            subscription.status in {SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL}
            and subscription.end_date < utc_now().date()
        ):
            raise HTTPException(
                status_code=422,
                detail="An active subscription cannot already be expired.",
            )

        self.db.commit()
        self.db.refresh(subscription)
        return subscription

    def cancel(self, tenant_id: UUID) -> Subscription:
        return self.update(tenant_id, {"status": SubscriptionStatus.CANCELLED})

    def serialize(self, subscription: Subscription) -> dict[str, Any]:
        tenant = cast(
            Tenant | None,
            self.db.scalar(
                _tenant_statement(
                    select(Tenant).where(Tenant.id == subscription.tenant_id),
                    "load organization name for subscription response",
                )
            ),
        )
        if tenant is None:
            raise HTTPException(status_code=404, detail="Organization not found.")
        return {
            "id": subscription.id,
            "tenant_id": subscription.tenant_id,
            "organization_name": tenant.name,
            "plan_name": subscription.plan_name,
            "status": subscription.status,
            "start_date": subscription.start_date,
            "end_date": subscription.end_date,
            "usage_limits": dict(subscription.usage_limits or {}),
            "features": dict(subscription.features or {}),
            "created_at": subscription.created_at,
            "updated_at": subscription.updated_at,
        }

    @staticmethod
    def plans() -> list[dict[str, Any]]:
        return [
            {
                "plan_name": plan_name,
                "usage_limits": dict(settings["usage_limits"]),
                "features": dict(settings["features"]),
            }
            for plan_name, settings in PLAN_CATALOG.items()
        ]

    def get_usage(self, tenant_id: UUID) -> dict[str, Any]:
        self.db.info["tenant_id"] = tenant_id
        existing_rows = _subscription_rows(self.db, tenant_id)
        subscription = next(
            (
                row
                for row in existing_rows
                if row.status in {SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL}
                and row.end_date >= utc_now().date()
            ),
            None,
        )
        if subscription is None:
            if existing_rows:
                subscription = existing_rows[0]
                if (
                    subscription.status
                    in {SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL}
                    and subscription.end_date < utc_now().date()
                ):
                    subscription.status = SubscriptionStatus.EXPIRED
                    self.db.commit()
                    self.db.refresh(subscription)
            else:
                subscription = _get_current_subscription(
                    self.db,
                    tenant_id,
                    create_trial_if_missing=False,
                    lock=False,
                )
        period_start = _period_start()
        period_end = _period_end(period_start)
        counter_statement = select(SubscriptionUsageCounter).where(
            SubscriptionUsageCounter.tenant_id == tenant_id,
            SubscriptionUsageCounter.period_start == period_start,
        )
        counters = cast(
            list[SubscriptionUsageCounter],
            list(
                self.db.scalars(
                    _tenant_statement(
                        counter_statement, "read tenant monthly subscription usage"
                    )
                ).all()
            ),
        )
        used_by_metric = {counter.metric: counter.used for counter in counters}

        active_users_query = select(func.count(User.id)).where(
            User.tenant_id == tenant_id,
            User.status == UserStatus.ACTIVE,
            User.is_deleted.is_(False),
        )
        raw_active_users = self.db.scalar(
            _tenant_statement(active_users_query, "report tenant active-user gauge")
        )
        active_users = int(cast(int | None, raw_active_users) or 0)
        storage_query = select(func.coalesce(func.sum(File.file_size), 0)).where(
            File.tenant_id == tenant_id
        )
        raw_storage_bytes = self.db.scalar(
            _tenant_statement(storage_query, "report tenant storage gauge")
        )
        storage_bytes = int(cast(int | None, raw_storage_bytes) or 0)
        current_values = {
            "api_calls": (used_by_metric.get("api_calls", 0), "calls"),
            "verification_checks": (
                used_by_metric.get("verification_checks", 0),
                "checks",
            ),
            "ai_requests": (used_by_metric.get("ai_requests", 0), "requests"),
            "transactions": (used_by_metric.get("transactions", 0), "transactions"),
            "active_users": (active_users, "users"),
            "storage_bytes": (storage_bytes, "bytes"),
        }
        metrics: list[SubscriptionUsageMetric] = []
        for metric, (used, unit) in current_values.items():
            limit_value = subscription.usage_limits.get(_LIMIT_KEY_BY_METRIC[metric])
            remaining = None if limit_value is None else max(limit_value - used, 0)
            metrics.append(
                SubscriptionUsageMetric(
                    metric=metric,
                    used=used,
                    limit=limit_value,
                    remaining=remaining,
                    unit=unit,
                )
            )
        return {
            "tenant_id": tenant_id,
            "subscription_id": subscription.id,
            "plan_name": subscription.plan_name,
            "status": subscription.status,
            "period_start": period_start,
            "period_end": period_end,
            "metrics": metrics,
        }
