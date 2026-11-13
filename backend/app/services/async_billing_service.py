"""Native-async billing plans, tenant assignments and immutable invoice snapshots."""

from __future__ import annotations

from calendar import monthrange
from datetime import timedelta
from decimal import Decimal
from typing import Any, TypedDict, cast
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.billing import BillingPlan, Invoice, InvoiceLineItem
from app.models.subscription import Subscription, SubscriptionUsageCounter
from app.models.tenant import Tenant
from app.schemas.billing import (
    BillingPlanAssignmentCreate,
    BillingPlanCreate,
    BillingPlanUpdate,
    InvoiceGenerateRequest,
)
from app.services.billing_service import (
    _add_months,
    _money,
    _period_month_starts,
    calculate_metered_quantity,
)
from app.services.subscription_service import PLAN_CATALOG
from app.utils.date_time import utc_now
from app.utils.enums import SubscriptionStatus
from app.utils.errors import bad_request, conflict, not_found

_ALLOWED_LIMITS = {
    "max_users",
    "api_calls",
    "verification_checks",
    "ai_requests",
    "transactions",
    "storage_bytes",
}
_METRIC_LABELS = {
    "api_calls": "API requests",
    "verification_checks": "Verification checks",
    "ai_requests": "AI analyses",
}


class InvoiceLineRow(TypedDict):
    description: str
    metric: str | None
    quantity: int
    unit_price: Decimal
    amount: Decimal


def _cross(statement, reason: str):
    return statement.execution_options(
        skip_tenant_filter=True, tenant_scope_reason=reason
    )


class AsyncBillingService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @staticmethod
    def _plan_limits(data: BillingPlanCreate) -> dict[str, int | None]:
        unknown = set(data.limits) - _ALLOWED_LIMITS
        if unknown:
            raise bad_request(f"Unsupported limit keys: {', '.join(sorted(unknown))}.")
        limits = dict(PLAN_CATALOG[data.subscription_tier]["usage_limits"])
        limits.update(data.limits)
        return limits

    @staticmethod
    def _plan_features(data: BillingPlanCreate) -> dict[str, bool]:
        result = dict(PLAN_CATALOG[data.subscription_tier]["features"])
        result.update(data.features)
        return result

    @staticmethod
    def _rate_json(rates: dict[str, Decimal]) -> dict[str, str]:
        return {metric: format(rate, "f") for metric, rate in rates.items()}

    async def list_plans(self, *, include_inactive: bool = False) -> list[BillingPlan]:
        stmt = select(BillingPlan)
        if not include_inactive:
            stmt = stmt.where(BillingPlan.status == "ACTIVE")
        rows = await self.db.scalars(stmt.order_by(BillingPlan.name.asc()))
        return list(rows.all())

    async def get_plan(self, plan_id: UUID, *, lock: bool = False) -> BillingPlan:
        stmt = select(BillingPlan).where(BillingPlan.id == plan_id)
        if lock:
            stmt = stmt.with_for_update()
        item = await self.db.scalar(stmt)
        if item is None:
            raise not_found("Billing plan")
        return item

    async def _find_plan(self, name: str) -> BillingPlan | None:
        return await self.db.scalar(
            select(BillingPlan).where(func.lower(BillingPlan.name) == name.lower())
        )

    async def _has_active_assignment(self, plan_id: UUID) -> bool:
        stmt = _cross(
            select(Subscription.id)
            .where(
                Subscription.billing_plan_id == plan_id,
                Subscription.status.in_(
                    [SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL]
                ),
                Subscription.end_date >= utc_now().date(),
            )
            .limit(1),
            "check all tenants for active billing plan assignments",
        )
        return await self.db.scalar(stmt) is not None

    async def create_plan(self, data: BillingPlanCreate) -> BillingPlan:
        if await self._find_plan(data.name):
            raise conflict("A billing plan with this name already exists.")
        item = BillingPlan(
            name=data.name,
            description=data.description,
            pricing_model=data.pricing_model,
            billing_interval=data.billing_interval,
            subscription_tier=data.subscription_tier,
            currency=data.currency,
            base_fee=_money(data.base_fee),
            unit_rates=self._rate_json(data.unit_rates),
            included_units=dict(data.included_units),
            limits=self._plan_limits(data),
            features=self._plan_features(data),
            status=data.status,
        )
        self.db.add(item)
        try:
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            raise conflict("A billing plan with this name already exists.") from exc
        await self.db.refresh(item)
        return item

    async def update_plan(
        self, plan_id: UUID, changes: BillingPlanUpdate
    ) -> BillingPlan:
        item = await self.get_plan(plan_id, lock=True)
        if "name" in changes.model_fields_set and changes.name is not None:
            other = await self._find_plan(changes.name)
            if other is not None and other.id != item.id:
                raise conflict("A billing plan with this name already exists.")
        price_fields = {
            "pricing_model",
            "billing_interval",
            "subscription_tier",
            "currency",
            "base_fee",
            "unit_rates",
            "included_units",
            "limits",
            "features",
        }
        if price_fields.intersection(
            changes.model_fields_set
        ) and await self._has_active_assignment(item.id):
            raise conflict(
                "This plan has active customer assignments. Create a new plan "
                "and reassign customers rather than changing its price terms in place."
            )
        merged: dict[str, Any] = {
            key: getattr(item, key)
            for key in (
                "name",
                "description",
                "pricing_model",
                "billing_interval",
                "subscription_tier",
                "currency",
                "base_fee",
                "unit_rates",
                "included_units",
                "limits",
                "features",
                "status",
            )
        }
        merged.update(changes.model_dump(exclude_unset=True))
        try:
            validated = BillingPlanCreate.model_validate(merged)
        except Exception as exc:
            raise bad_request(f"Invalid billing plan update: {exc}") from exc
        item.name, item.description = validated.name, validated.description
        item.pricing_model, item.billing_interval = (
            validated.pricing_model,
            validated.billing_interval,
        )
        item.subscription_tier, item.currency = (
            validated.subscription_tier,
            validated.currency,
        )
        item.base_fee, item.unit_rates = (
            _money(validated.base_fee),
            self._rate_json(validated.unit_rates),
        )
        item.included_units, item.limits, item.features, item.status = (
            dict(validated.included_units),
            self._plan_limits(validated),
            self._plan_features(validated),
            validated.status,
        )
        try:
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            raise conflict("A billing plan with this name already exists.") from exc
        await self.db.refresh(item)
        return item

    async def _tenant(self, tenant_id: UUID) -> Tenant:
        item = cast(
            Tenant | None,
            await self.db.scalar(
                _cross(
                    select(Tenant).where(Tenant.id == tenant_id),
                    "resolve one explicitly selected tenant for platform billing",
                )
            ),
        )

        if item is None:
            raise not_found("Customer tenant")

        return item

    async def _subscriptions(
        self, tenant_id: UUID, *, lock: bool = False
    ) -> list[Subscription]:
        stmt = _cross(
            select(Subscription)
            .where(Subscription.tenant_id == tenant_id)
            .order_by(Subscription.created_at.desc()),
            "load subscription rows for an explicit tenant billing operation",
        )
        if lock:
            stmt = stmt.with_for_update()
        rows = await self.db.scalars(stmt)
        return list(rows.all())

    async def assign_plan(self, data: BillingPlanAssignmentCreate) -> dict[str, object]:
        await self._tenant(data.tenant_id)
        plan = await self.get_plan(data.billing_plan_id, lock=True)
        if plan.status != "ACTIVE":
            raise bad_request("An inactive billing plan cannot be assigned.")
        today = utc_now().date()
        start = data.start_date or today.replace(day=1)
        end = data.end_date or (_add_months(start, 12) - timedelta(days=1))
        if (
            start.day != 1
            or end.day != monthrange(end.year, end.month)[1]
            or end < start
        ):
            raise bad_request(
                "Billing assignments must cover complete calendar months."
            )
        if end < today:
            raise bad_request("The billing assignment end date is in the past.")
        months = _period_month_starts(start, end)
        if plan.billing_interval == "ANNUAL" and len(months) % 12 != 0:
            raise bad_request(
                "ANNUAL plan assignments must cover complete 12-calendar-month periods."
            )
        self.db.info["tenant_id"] = data.tenant_id
        existing = await self._subscriptions(data.tenant_id, lock=True)
        for row in existing:
            if row.status in {SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL}:
                if row.end_date < today:
                    row.status = SubscriptionStatus.EXPIRED
                else:
                    row.status = SubscriptionStatus.CANCELLED
                    if row.start_date < start:
                        row.end_date = min(row.end_date, start - timedelta(days=1))
        limits = dict(plan.limits or {})
        limits.update(data.usage_limit_overrides)
        item = Subscription(
            tenant_id=data.tenant_id,
            plan_name=plan.subscription_tier,
            status=SubscriptionStatus.ACTIVE,
            start_date=start,
            end_date=end,
            usage_limits=limits,
            features=dict(plan.features or {}),
            billing_plan_id=plan.id,
        )
        self.db.add(item)
        try:
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            raise conflict(
                "A concurrent subscription assignment was created "
                "for this tenant. Retry the assignment."
            ) from exc
        await self.db.refresh(item)
        return {
            "tenant_id": data.tenant_id,
            "subscription_id": item.id,
            "billing_plan_id": plan.id,
            "billing_plan_name": plan.name,
            "plan_name": item.plan_name,
            "status": item.status.value,
            "start_date": item.start_date,
            "end_date": item.end_date,
            "usage_limits": dict(item.usage_limits or {}),
            "features": dict(item.features or {}),
        }

    async def get_assignment(self, tenant_id: UUID) -> dict[str, object]:
        rows = await self._subscriptions(tenant_id)
        item = next(
            (
                row
                for row in rows
                if row.status in {SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL}
                and row.end_date >= utc_now().date()
                and row.billing_plan_id is not None
            ),
            None,
        )
        if item is None or item.billing_plan_id is None:
            raise not_found("Current billing plan assignment")
        plan = await self.get_plan(item.billing_plan_id)
        return {
            "tenant_id": tenant_id,
            "subscription_id": item.id,
            "billing_plan_id": plan.id,
            "billing_plan_name": plan.name,
            "plan_name": item.plan_name,
            "status": item.status.value,
            "start_date": item.start_date,
            "end_date": item.end_date,
            "usage_limits": dict(item.usage_limits or {}),
            "features": dict(item.features or {}),
        }

    async def generate_invoice(self, data: InvoiceGenerateRequest) -> Invoice:
        await self._tenant(data.tenant_id)
        months = _period_month_starts(data.period_start, data.period_end)
        start, end = data.period_start, data.period_end
        if start.day != 1 or end.day != monthrange(end.year, end.month)[1]:
            raise bad_request(
                "Invoice periods must start on the first and "
                "end on the last day of a month."
            )
        self.db.info["tenant_id"] = data.tenant_id
        stmt = _cross(
            select(Subscription)
            .where(
                Subscription.tenant_id == data.tenant_id,
                Subscription.start_date <= start,
                Subscription.end_date >= end,
                Subscription.billing_plan_id.is_not(None),
            )
            .order_by(Subscription.created_at.desc())
            .with_for_update(),
            "resolve subscription covering explicit invoice tenant and full period",
        )
        subscription = await self.db.scalar(stmt)
        if subscription is None or subscription.billing_plan_id is None:
            raise not_found("Billing plan assignment covering the requested period")
        existing_stmt = _cross(
            select(Invoice)
            .options(selectinload(Invoice.line_items))
            .where(
                Invoice.tenant_id == data.tenant_id,
                Invoice.period_start == start,
                Invoice.period_end == end,
            ),
            "idempotency lookup for one explicit tenant invoice period",
        )
        existing = cast(
            Invoice | None,
            await self.db.scalar(existing_stmt),
        )
        if existing is not None:
            return existing
        plan = await self.get_plan(subscription.billing_plan_id)
        if plan.billing_interval == "MONTHLY" and len(months) != 1:
            raise bad_request(
                "MONTHLY plans require an invoice period of one calendar month."
            )
        if plan.billing_interval == "ANNUAL" and len(months) != 12:
            raise bad_request(
                "ANNUAL plans require an invoice period of 12 full calendar months."
            )
        if plan.pricing_model == "USAGE_BASED" and len(months) != 1:
            raise bad_request(
                "USAGE_BASED plans must be invoiced one calendar month at a time."
            )
        counter_stmt = _cross(
            select(SubscriptionUsageCounter).where(
                SubscriptionUsageCounter.tenant_id == data.tenant_id,
                SubscriptionUsageCounter.period_start.in_(months),
                SubscriptionUsageCounter.metric.in_(list(_METRIC_LABELS)),
            ),
            "read usage counters for the explicit invoice tenant and months",
        )
        rows = await self.db.scalars(counter_stmt)
        usage = {(row.period_start, row.metric): row.used for row in rows.all()}
        line_rows: list[InvoiceLineRow] = []
        base_fee = Decimal(str(plan.base_fee or 0))
        if base_fee > 0:
            period_label = (
                "monthly"
                if plan.billing_interval == "MONTHLY"
                else (
                    "annual"
                    if plan.billing_interval == "ANNUAL"
                    else "custom enterprise"
                )
            )
            line_rows.append(
                {
                    "description": f"{plan.name} {period_label} subscription fee",
                    "metric": None,
                    "quantity": 1,
                    "unit_price": base_fee,
                    "amount": _money(base_fee),
                }
            )
        for metric, raw_rate in sorted((plan.unit_rates or {}).items()):
            if metric not in _METRIC_LABELS:
                raise bad_request(
                    f"Billing plan has unsupported metric rate: {metric}."
                )
            quantity = calculate_metered_quantity(
                month_starts=months,
                usage_by_month_metric=usage,
                metric=metric,
                included_units_per_month=int(
                    (plan.included_units or {}).get(metric, 0)
                ),
            )
            rate = Decimal(str(raw_rate))
            line_rows.append(
                {
                    "description": (
                        f"{_METRIC_LABELS[metric]} above included "
                        "allowance ({quantity} billable)"
                    ),
                    "metric": metric,
                    "quantity": quantity,
                    "unit_price": rate,
                    "amount": _money(rate * quantity),
                }
            )
        total = _money(sum((row["amount"] for row in line_rows), Decimal("0")))
        invoice = Invoice(
            id=uuid4(),
            tenant_id=data.tenant_id,
            subscription_id=subscription.id,
            billing_plan_id=plan.id,
            invoice_number=f"FP-{start:%Y%m}-{uuid4().hex[:8].upper()}",
            plan_name_snapshot=plan.name,
            period_start=start,
            period_end=end,
            amount=total,
            currency=plan.currency,
            status="DRAFT",
            due_date=end + timedelta(days=data.due_days),
        )
        self.db.add(invoice)
        for line_row in line_rows:
            self.db.add(
                InvoiceLineItem(
                    id=uuid4(),
                    tenant_id=data.tenant_id,
                    invoice_id=invoice.id,
                    description=str(line_row["description"]),
                    metric=line_row["metric"],
                    quantity=int(line_row["quantity"]),
                    unit_price=Decimal(line_row["unit_price"]),
                    amount=Decimal(line_row["amount"]),
                )
            )
        try:
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            retry = cast(
                Invoice | None,
                await self.db.scalar(existing_stmt),
            )
            if retry is not None:
                return retry
            raise conflict(
                "An invoice for this subscription period already exists."
            ) from exc
        result = cast(
            Invoice | None,
            await self.db.scalar(
                _cross(
                    select(Invoice)
                    .options(selectinload(Invoice.line_items))
                    .where(
                        Invoice.id == invoice.id,
                        Invoice.tenant_id == data.tenant_id,
                    ),
                    "reload generated invoice for explicit tenant",
                )
            ),
        )
        if result is None:
            raise not_found("Generated invoice")
        return result

    async def list_invoices(
        self, tenant_id: UUID, *, limit: int = 100
    ) -> list[dict[str, object]]:
        stmt = _cross(
            select(Invoice)
            .options(selectinload(Invoice.line_items))
            .where(Invoice.tenant_id == tenant_id)
            .order_by(Invoice.created_at.desc())
            .limit(limit),
            "list invoices for one explicitly authorized tenant",
        )
        rows = await self.db.scalars(stmt)
        return [self.serialize_invoice(row) for row in rows.all()]

    async def get_invoice(self, invoice_id: UUID, tenant_id: UUID) -> dict[str, object]:
        stmt = _cross(
            select(Invoice)
            .options(selectinload(Invoice.line_items))
            .where(Invoice.id == invoice_id, Invoice.tenant_id == tenant_id),
            "read one invoice for an explicitly authorized tenant",
        )
        item = await self.db.scalar(stmt)
        if item is None:
            raise not_found("Invoice")
        return self.serialize_invoice(item)

    async def update_invoice_status(
        self, *, invoice_id: UUID, tenant_id: UUID, next_status: str
    ) -> dict[str, object]:
        stmt = _cross(
            select(Invoice)
            .options(selectinload(Invoice.line_items))
            .where(Invoice.id == invoice_id, Invoice.tenant_id == tenant_id)
            .with_for_update(),
            "update one invoice for an explicitly authorized tenant",
        )
        item = await self.db.scalar(stmt)
        if item is None:
            raise not_found("Invoice")
        allowed = {
            "DRAFT": {"ISSUED", "VOID"},
            "ISSUED": {"PAID", "VOID"},
            "PAID": set(),
            "VOID": set(),
        }
        if next_status != item.status and next_status not in allowed.get(
            item.status, set()
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Invoice cannot transition from {item.status} to {next_status}."
                ),
            )
        previous_tenant = self.db.info.get("tenant_id")
        self.db.info["tenant_id"] = tenant_id
        try:
            now = utc_now()
            if next_status == "ISSUED":
                item.issued_at = now
            elif next_status == "PAID":
                item.paid_at = now
            item.status = next_status
            await self.db.commit()
            refreshed = await self.db.scalar(
                _cross(
                    select(Invoice)
                    .options(selectinload(Invoice.line_items))
                    .where(Invoice.id == invoice_id, Invoice.tenant_id == tenant_id),
                    "reload updated invoice for explicit tenant",
                )
            )
            if refreshed is None:
                raise not_found("Invoice")
            return self.serialize_invoice(refreshed)
        except Exception:
            await self.db.rollback()
            raise
        finally:
            if previous_tenant is None:
                self.db.info.pop("tenant_id", None)
            else:
                self.db.info["tenant_id"] = previous_tenant

    @staticmethod
    def serialize_invoice(invoice: Invoice) -> dict[str, object]:
        today = utc_now().date()
        return {
            "id": invoice.id,
            "tenant_id": invoice.tenant_id,
            "subscription_id": invoice.subscription_id,
            "billing_plan_id": invoice.billing_plan_id,
            "invoice_number": invoice.invoice_number,
            "plan_name_snapshot": invoice.plan_name_snapshot,
            "period_start": invoice.period_start,
            "period_end": invoice.period_end,
            "amount": invoice.amount,
            "currency": invoice.currency,
            "status": invoice.status,
            "due_date": invoice.due_date,
            "issued_at": invoice.issued_at,
            "paid_at": invoice.paid_at,
            "created_at": invoice.created_at,
            "updated_at": invoice.updated_at,
            "is_overdue": invoice.status == "ISSUED" and invoice.due_date < today,
            "line_items": [
                {
                    "id": row.id,
                    "description": row.description,
                    "metric": row.metric,
                    "quantity": row.quantity,
                    "unit_price": row.unit_price,
                    "amount": row.amount,
                    "created_at": row.created_at,
                }
                for row in invoice.line_items
            ],
        }
