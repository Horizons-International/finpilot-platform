"""Persistence access for platform billing and tenant-owned invoice records."""

from datetime import date
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.billing import BillingPlan, Invoice, InvoiceLineItem
from app.models.subscription import Subscription, SubscriptionUsageCounter
from app.models.tenant import Tenant
from app.utils.enums import SubscriptionStatus


class BillingRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_plans(self, *, include_inactive: bool = False) -> list[BillingPlan]:
        statement = select(BillingPlan)
        if not include_inactive:
            statement = statement.where(BillingPlan.status == "ACTIVE")
        return list(self.db.scalars(statement.order_by(BillingPlan.name.asc())).all())

    def get_plan(
        self, plan_id: UUID, *, for_update: bool = False
    ) -> BillingPlan | None:
        statement = select(BillingPlan).where(BillingPlan.id == plan_id)
        if for_update:
            statement = statement.with_for_update()
        return self.db.scalar(statement)

    def find_plan_by_name(self, name: str) -> BillingPlan | None:
        return self.db.scalar(
            select(BillingPlan).where(func.lower(BillingPlan.name) == name.lower())
        )

    def has_active_assignment(self, billing_plan_id: UUID, *, today: date) -> bool:
        """Check assignment across tenants before allowing an in-place price edit."""
        statement = (
            select(Subscription.id)
            .where(
                Subscription.billing_plan_id == billing_plan_id,
                Subscription.status.in_(
                    [SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL]
                ),
                Subscription.end_date >= today,
            )
            .limit(1)
            .execution_options(
                skip_tenant_filter=True,
                tenant_scope_reason=(
                    "platform-admin checks whether billing price terms are assigned "
                    "across customer tenants before mutation"
                ),
            )
        )
        return self.db.scalar(statement) is not None

    def get_tenant(self, tenant_id: UUID) -> Tenant | None:
        statement = (
            select(Tenant)
            .where(Tenant.id == tenant_id)
            .execution_options(
                skip_tenant_filter=True,
                tenant_scope_reason=(
                    "platform-admin billing assignment resolves explicit "
                    "customer tenant"
                ),
            )
        )
        return self.db.scalar(statement)

    def list_subscriptions(
        self, tenant_id: UUID, *, for_update: bool = False
    ) -> list[Subscription]:
        statement = (
            select(Subscription)
            .where(Subscription.tenant_id == tenant_id)
            .order_by(Subscription.created_at.desc())
            .execution_options(
                skip_tenant_filter=True,
                tenant_scope_reason=(
                    "platform-admin billing operation loads subscriptions "
                    "for one tenant"
                ),
            )
        )
        if for_update:
            statement = statement.with_for_update()
        return list(self.db.scalars(statement).all())

    def list_usage_counters(
        self, tenant_id: UUID, period_starts: list[date]
    ) -> list[SubscriptionUsageCounter]:
        if not period_starts:
            return []
        statement = (
            select(SubscriptionUsageCounter)
            .where(
                SubscriptionUsageCounter.tenant_id == tenant_id,
                SubscriptionUsageCounter.period_start.in_(period_starts),
                SubscriptionUsageCounter.metric.in_(
                    ["api_calls", "verification_checks", "ai_requests"]
                ),
            )
            .execution_options(
                skip_tenant_filter=True,
                tenant_scope_reason=(
                    "invoice calculation reads monthly usage for the specified tenant"
                ),
            )
        )
        return list(self.db.scalars(statement).all())

    def find_invoice_for_period(
        self,
        *,
        tenant_id: UUID,
        period_start: date,
        period_end: date,
    ) -> Invoice | None:
        statement = (
            select(Invoice)
            .options(selectinload(Invoice.line_items))
            .where(
                Invoice.tenant_id == tenant_id,
                Invoice.period_start == period_start,
                Invoice.period_end == period_end,
            )
            .execution_options(
                skip_tenant_filter=True,
                tenant_scope_reason=(
                    "invoice idempotency check for one explicit tenant billing period"
                ),
            )
        )
        return self.db.scalar(statement)

    def get_invoice(self, invoice_id: UUID, tenant_id: UUID) -> Invoice | None:
        statement = (
            select(Invoice)
            .options(selectinload(Invoice.line_items))
            .where(Invoice.id == invoice_id, Invoice.tenant_id == tenant_id)
            .execution_options(
                skip_tenant_filter=True,
                tenant_scope_reason=(
                    "read an invoice for one explicitly authorized tenant"
                ),
            )
        )
        return self.db.scalar(statement)

    def list_invoices(self, tenant_id: UUID, *, limit: int = 100) -> list[Invoice]:
        statement = (
            select(Invoice)
            .options(selectinload(Invoice.line_items))
            .where(Invoice.tenant_id == tenant_id)
            .order_by(Invoice.created_at.desc())
            .limit(limit)
            .execution_options(
                skip_tenant_filter=True,
                tenant_scope_reason=(
                    "list invoices for one explicitly authorized tenant"
                ),
            )
        )
        return list(self.db.scalars(statement).unique().all())

    def add_invoice(self, invoice: Invoice) -> Invoice:
        self.db.add(invoice)
        self.db.flush()
        return invoice

    def add_line_items(self, items: list[InvoiceLineItem]) -> None:
        self.db.add_all(items)
        self.db.flush()
