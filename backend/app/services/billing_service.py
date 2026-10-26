"""Platform billing use cases, metered charge calculation, and invoice lifecycle."""

from calendar import monthrange
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import TypedDict
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.billing import BillingPlan, Invoice, InvoiceLineItem
from app.models.subscription import Subscription
from app.repositories.billing_repository import BillingRepository
from app.schemas.billing import (
    BillingPlanAssignmentCreate,
    BillingPlanCreate,
    BillingPlanUpdate,
    InvoiceGenerateRequest,
)
from app.services.subscription_service import PLAN_CATALOG
from app.utils.date_time import utc_now
from app.utils.enums import SubscriptionStatus
from app.utils.errors import bad_request, conflict, not_found

_CENT = Decimal("0.01")
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


def _money(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def _month_start(value: date) -> date:
    return value.replace(day=1)


def _add_months(value: date, months: int) -> date:
    """Add calendar months; callers use first-of-month values."""
    offset = value.year * 12 + value.month - 1 + months
    year, month_zero_based = divmod(offset, 12)
    return date(year, month_zero_based + 1, 1)


def _period_month_starts(start: date, end: date) -> list[date]:
    result: list[date] = []
    cursor = _month_start(start)
    last = _month_start(end)
    while cursor <= last:
        result.append(cursor)
        cursor = _add_months(cursor, 1)
    return result


def calculate_metered_quantity(
    *,
    month_starts: list[date],
    usage_by_month_metric: dict[tuple[date, str], int],
    metric: str,
    included_units_per_month: int,
) -> int:
    """Bill each full calendar month's usage above that month's included allowance."""
    return sum(
        max(usage_by_month_metric.get((month, metric), 0) - included_units_per_month, 0)
        for month in month_starts
    )


class BillingService:
    """Business operations for platform-defined prices and tenant invoice records."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = BillingRepository(db)

    @staticmethod
    def _plan_limits(data: BillingPlanCreate) -> dict[str, int | None]:
        limits = dict(PLAN_CATALOG[data.subscription_tier]["usage_limits"])
        unknown = set(data.limits) - _ALLOWED_LIMITS
        if unknown:
            raise bad_request(f"Unsupported limit keys: {', '.join(sorted(unknown))}.")
        limits.update(data.limits)
        return limits

    @staticmethod
    def _plan_features(data: BillingPlanCreate) -> dict[str, bool]:
        features = dict(PLAN_CATALOG[data.subscription_tier]["features"])
        features.update(data.features)
        return features

    @staticmethod
    def _rate_json(rates: dict[str, Decimal]) -> dict[str, str]:
        return {metric: format(rate, "f") for metric, rate in rates.items()}

    def list_plans(self, *, include_inactive: bool = False) -> list[BillingPlan]:
        return self.repository.list_plans(include_inactive=include_inactive)

    def get_plan(self, plan_id: UUID) -> BillingPlan:
        plan = self.repository.get_plan(plan_id)
        if plan is None:
            raise not_found("Billing plan")
        return plan

    def create_plan(self, data: BillingPlanCreate) -> BillingPlan:
        if self.repository.find_plan_by_name(data.name) is not None:
            raise conflict("A billing plan with this name already exists.")

        plan = BillingPlan(
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
        try:
            self.db.add(plan)
            self.db.commit()
            self.db.refresh(plan)
            return plan
        except IntegrityError as exc:
            self.db.rollback()
            raise conflict("A billing plan with this name already exists.") from exc

    def update_plan(self, plan_id: UUID, changes: BillingPlanUpdate) -> BillingPlan:
        plan = self.repository.get_plan(plan_id, for_update=True)
        if plan is None:
            raise not_found("Billing plan")

        if "name" in changes.model_fields_set and changes.name is not None:
            other = self.repository.find_plan_by_name(changes.name)
            if other is not None and other.id != plan.id:
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
        if price_fields.intersection(changes.model_fields_set) and (
            self.repository.has_active_assignment(plan.id, today=utc_now().date())
        ):
            raise conflict(
                "This plan has active customer assignments. Create a new plan and "
                "reassign customers rather than changing its price terms in place."
            )

        merged: dict[str, object] = {
            "name": plan.name,
            "description": plan.description,
            "pricing_model": plan.pricing_model,
            "billing_interval": plan.billing_interval,
            "subscription_tier": plan.subscription_tier,
            "currency": plan.currency,
            "base_fee": plan.base_fee,
            "unit_rates": dict(plan.unit_rates or {}),
            "included_units": dict(plan.included_units or {}),
            "limits": dict(plan.limits or {}),
            "features": dict(plan.features or {}),
            "status": plan.status,
        }
        merged.update(changes.model_dump(exclude_unset=True))
        try:
            validated = BillingPlanCreate.model_validate(merged)
        except Exception as exc:
            raise bad_request(f"Invalid billing plan update: {exc}") from exc

        plan.name = validated.name
        plan.description = validated.description
        plan.pricing_model = validated.pricing_model
        plan.billing_interval = validated.billing_interval
        plan.subscription_tier = validated.subscription_tier
        plan.currency = validated.currency
        plan.base_fee = _money(validated.base_fee)
        plan.unit_rates = self._rate_json(validated.unit_rates)
        plan.included_units = dict(validated.included_units)
        plan.limits = self._plan_limits(validated)
        plan.features = self._plan_features(validated)
        plan.status = validated.status
        try:
            self.db.commit()
            self.db.refresh(plan)
            return plan
        except IntegrityError as exc:
            self.db.rollback()
            raise conflict("A billing plan with this name already exists.") from exc

    def assign_plan(self, data: BillingPlanAssignmentCreate) -> dict[str, object]:
        tenant = self.repository.get_tenant(data.tenant_id)
        if tenant is None:
            raise not_found("Customer tenant")
        plan = self.repository.get_plan(data.billing_plan_id, for_update=True)
        if plan is None:
            raise not_found("Billing plan")
        if plan.status != "ACTIVE":
            raise bad_request("An inactive billing plan cannot be assigned.")

        today = utc_now().date()
        selected_start = data.start_date or _month_start(today)
        selected_end = data.end_date or (
            _add_months(selected_start, 12) - timedelta(days=1)
        )
        if selected_start.day != 1:
            raise bad_request("start_date must be the first day of a calendar month.")
        if selected_end.day != monthrange(selected_end.year, selected_end.month)[1]:
            raise bad_request("end_date must be the last day of a calendar month.")
        if selected_end < selected_start:
            raise bad_request("end_date must be on or after start_date.")
        if selected_end < today:
            raise bad_request("The billing assignment end date is in the past.")
        if plan.billing_interval == "ANNUAL" and (
            len(_period_month_starts(selected_start, selected_end)) % 12 != 0
        ):
            raise bad_request(
                "ANNUAL plan assignments must cover complete 12-calendar-month periods."
            )

        # Cross-tenant writes below are limited to the explicit target tenant and
        # occur only through endpoints protected by require_platform_admin.
        self.db.info["tenant_id"] = data.tenant_id
        subscriptions = self.repository.list_subscriptions(
            data.tenant_id, for_update=True
        )
        current_date = today
        for existing in subscriptions:
            if existing.status in {SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL}:
                if existing.end_date < current_date:
                    existing.status = SubscriptionStatus.EXPIRED
                else:
                    existing.status = SubscriptionStatus.CANCELLED
                    if existing.start_date < selected_start:
                        existing.end_date = min(
                            existing.end_date, selected_start - timedelta(days=1)
                        )

        limits = dict(plan.limits or {})
        limits.update(data.usage_limit_overrides)
        new_subscription = Subscription(
            tenant_id=data.tenant_id,
            plan_name=plan.subscription_tier,
            status=SubscriptionStatus.ACTIVE,
            start_date=selected_start,
            end_date=selected_end,
            usage_limits=limits,
            features=dict(plan.features or {}),
            billing_plan_id=plan.id,
        )
        try:
            self.db.add(new_subscription)
            self.db.commit()
            self.db.refresh(new_subscription)
        except IntegrityError as exc:
            self.db.rollback()
            raise conflict(
                "A concurrent subscription assignment was created for this tenant. "
                "Retry the assignment."
            ) from exc
        except Exception:
            self.db.rollback()
            raise

        return {
            "tenant_id": data.tenant_id,
            "subscription_id": new_subscription.id,
            "billing_plan_id": plan.id,
            "billing_plan_name": plan.name,
            "plan_name": new_subscription.plan_name,
            "status": new_subscription.status.value,
            "start_date": new_subscription.start_date,
            "end_date": new_subscription.end_date,
            "usage_limits": dict(new_subscription.usage_limits or {}),
            "features": dict(new_subscription.features or {}),
        }

    def get_assignment(self, tenant_id: UUID) -> dict[str, object]:
        subscriptions = self.repository.list_subscriptions(tenant_id)
        subscription = next(
            (
                item
                for item in subscriptions
                if item.status in {SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL}
                and item.end_date >= utc_now().date()
                and item.billing_plan_id is not None
            ),
            None,
        )
        if subscription is None or subscription.billing_plan_id is None:
            raise not_found("Current billing plan assignment")
        plan = self.get_plan(subscription.billing_plan_id)
        return {
            "tenant_id": tenant_id,
            "subscription_id": subscription.id,
            "billing_plan_id": plan.id,
            "billing_plan_name": plan.name,
            "plan_name": subscription.plan_name,
            "status": subscription.status.value,
            "start_date": subscription.start_date,
            "end_date": subscription.end_date,
            "usage_limits": dict(subscription.usage_limits or {}),
            "features": dict(subscription.features or {}),
        }

    def generate_invoice(self, data: InvoiceGenerateRequest) -> Invoice:
        tenant = self.repository.get_tenant(data.tenant_id)
        if tenant is None:
            raise not_found("Customer tenant")

        start = data.period_start
        end = data.period_end
        months = _period_month_starts(start, end)
        # Usage counters are stored per full calendar month, so billing never
        # prorates a month of usage based on unsupported assumptions.
        if start.day != 1 or end.day != monthrange(end.year, end.month)[1]:
            raise bad_request(
                "Invoice periods must start on the first and end on the last "
                "day of a month."
            )

        self.db.info["tenant_id"] = data.tenant_id
        statement = (
            select(Subscription)
            .where(
                Subscription.tenant_id == data.tenant_id,
                Subscription.start_date <= start,
                Subscription.end_date >= end,
                Subscription.billing_plan_id.is_not(None),
            )
            .order_by(Subscription.created_at.desc())
            .with_for_update()
            .execution_options(
                skip_tenant_filter=True,
                tenant_scope_reason=(
                    "platform-admin invoice calculation resolves subscription "
                    "covering one tenant period"
                ),
            )
        )
        subscription = self.db.scalar(statement)
        if subscription is None or subscription.billing_plan_id is None:
            raise not_found("Billing plan assignment covering the requested period")

        existing = self.repository.find_invoice_for_period(
            tenant_id=data.tenant_id,
            period_start=start,
            period_end=end,
        )
        if existing is not None:
            # Idempotent retries return the original immutable invoice snapshot.
            return existing

        plan = self.repository.get_plan(subscription.billing_plan_id)
        if plan is None:
            raise not_found("Billing plan")
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

        counter_rows = self.repository.list_usage_counters(data.tenant_id, months)
        usage_by_month_metric = {
            (row.period_start, row.metric): row.used for row in counter_rows
        }
        line_rows: list[InvoiceLineRow] = []
        base_fee = Decimal(str(plan.base_fee or 0))
        if base_fee > 0:
            if plan.billing_interval == "MONTHLY":
                description = f"{plan.name} monthly subscription fee"
            elif plan.billing_interval == "ANNUAL":
                description = f"{plan.name} annual subscription fee"
            else:
                description = f"{plan.name} custom enterprise base fee"
            line_rows.append(
                {
                    "description": description,
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
            included = int((plan.included_units or {}).get(metric, 0))
            quantity = calculate_metered_quantity(
                month_starts=months,
                usage_by_month_metric=usage_by_month_metric,
                metric=metric,
                included_units_per_month=included,
            )
            rate = Decimal(str(raw_rate))
            amount = _money(rate * quantity)
            label = _METRIC_LABELS[metric]
            line_rows.append(
                {
                    "description": (
                        f"{label} above included allowance ({quantity} billable)"
                    ),
                    "metric": metric,
                    "quantity": quantity,
                    "unit_price": rate,
                    "amount": amount,
                }
            )

        total = _money(
            sum(
                (row["amount"] for row in line_rows),
                Decimal("0"),
            )
        )
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
        try:
            self.repository.add_invoice(invoice)
            self.repository.add_line_items(
                [
                    InvoiceLineItem(
                        id=uuid4(),
                        tenant_id=data.tenant_id,
                        invoice_id=invoice.id,
                        description=row["description"],
                        metric=row["metric"],
                        quantity=row["quantity"],
                        unit_price=row["unit_price"],
                        amount=row["amount"],
                    )
                    for row in line_rows
                ]
            )
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            # A concurrent request may have generated the same period invoice.
            self.db.info["tenant_id"] = data.tenant_id
            retry = self.repository.find_invoice_for_period(
                tenant_id=data.tenant_id,
                period_start=start,
                period_end=end,
            )
            if retry is not None:
                return retry
            raise conflict("An invoice for this subscription period already exists.")
        except Exception:
            self.db.rollback()
            raise

        result = self.repository.get_invoice(invoice.id, data.tenant_id)
        if result is None:
            raise not_found("Generated invoice")
        return result

    def list_invoices(
        self, tenant_id: UUID, *, limit: int = 100
    ) -> list[dict[str, object]]:
        return [
            self.serialize_invoice(item)
            for item in self.repository.list_invoices(tenant_id, limit=limit)
        ]

    def get_invoice(self, invoice_id: UUID, tenant_id: UUID) -> dict[str, object]:
        invoice = self.repository.get_invoice(invoice_id, tenant_id)
        if invoice is None:
            raise not_found("Invoice")
        return self.serialize_invoice(invoice)

    def update_invoice_status(
        self, *, invoice_id: UUID, tenant_id: UUID, next_status: str
    ) -> dict[str, object]:
        self.db.info["tenant_id"] = tenant_id
        invoice = self.repository.get_invoice(invoice_id, tenant_id)
        if invoice is None:
            raise not_found("Invoice")
        allowed = {
            "DRAFT": {"ISSUED", "VOID"},
            "ISSUED": {"PAID", "VOID"},
            "PAID": set(),
            "VOID": set(),
        }
        if next_status == invoice.status:
            return self.serialize_invoice(invoice)
        if next_status not in allowed.get(invoice.status, set()):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Invoice cannot transition from {invoice.status} to {next_status}."
                ),
            )
        now = utc_now()
        invoice.status = next_status
        if next_status == "ISSUED":
            invoice.issued_at = now
        elif next_status == "PAID":
            invoice.paid_at = now
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        refreshed = self.repository.get_invoice(invoice_id, tenant_id)
        if refreshed is None:
            raise not_found("Invoice")
        return self.serialize_invoice(refreshed)

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
                    "id": item.id,
                    "description": item.description,
                    "metric": item.metric,
                    "quantity": item.quantity,
                    "unit_price": item.unit_price,
                    "amount": item.amount,
                    "created_at": item.created_at,
                }
                for item in invoice.line_items
            ],
        }
