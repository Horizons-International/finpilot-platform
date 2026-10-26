"""Integration coverage for plan assignment and invoice generation."""

from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from app.models.billing import BillingPlan, Invoice, InvoiceLineItem
from app.models.subscription import Subscription, SubscriptionUsageCounter
from app.models.tenant import Tenant
from app.services.billing_service import calculate_metered_quantity
from app.utils.enums import UserRole
from tests.conftest import TestSessionLocal
from tests.helpers import authenticate_client


def _month_start(today: date) -> date:
    return today.replace(day=1)


def _add_months(value: date, months: int) -> date:
    offset = value.year * 12 + value.month - 1 + months
    year, month_zero_based = divmod(offset, 12)
    return date(year, month_zero_based + 1, 1)


def test_metering_calculation_applies_included_allowance_per_month() -> None:
    months = [date(2026, 9, 1), date(2026, 10, 1)]
    usage = {
        (date(2026, 9, 1), "api_calls"): 12_000,
        (date(2026, 10, 1), "api_calls"): 8_000,
    }

    billed = calculate_metered_quantity(
        month_starts=months,
        usage_by_month_metric=usage,
        metric="api_calls",
        included_units_per_month=10_000,
    )

    assert billed == 2_000


def test_plan_assignment_and_invoice_lifecycle(client, create_test_user) -> None:
    """One isolated customer tenant prevents affecting shared DEFAULT subscription."""
    admin = create_test_user(
        role=UserRole.ADMINISTRATOR.value,
        email=f"billing-admin-{uuid4()}@example.com",
        is_platform_admin=True,
    )
    authenticate_client(client, admin)

    tenant_code = f"BILL-{uuid4().hex[:12].upper()}"
    plan_name = f"Test Billing {uuid4().hex[:8]}"
    db = TestSessionLocal()
    tenant_id = None
    plan_id = None
    try:
        tenant = Tenant(name="Billing Test Bank", code=tenant_code)
        db.add(tenant)
        db.commit()
        db.refresh(tenant)
        tenant_id = tenant.id
    finally:
        db.close()

    try:
        response = client.post(
            "/api/v1/billing/plans",
            json={
                "name": plan_name,
                "pricing_model": "USAGE_BASED",
                "billing_interval": "MONTHLY",
                "subscription_tier": "professional",
                "currency": "USD",
                "base_fee": "100.00",
                "included_units": {
                    "api_calls": 0,
                    "verification_checks": 0,
                    "ai_requests": 0,
                },
                "unit_rates": {
                    "api_calls": "0.001",
                    "verification_checks": "0.10",
                    "ai_requests": "0.25",
                },
            },
        )
        assert response.status_code == 201, response.text
        plan_id = UUID(response.json()["data"]["id"])

        today = date.today()
        start = _month_start(today)
        end = _add_months(start, 12) - timedelta(days=1)
        assignment = client.post(
            "/api/v1/billing/assignments",
            json={
                "tenant_id": str(tenant_id),
                "billing_plan_id": str(plan_id),
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
            },
        )
        assert assignment.status_code == 201, assignment.text

        # Active customers keep their agreed price; create a new plan to change it.
        rejected_price_edit = client.patch(
            f"/api/v1/billing/plans/{plan_id}",
            json={"base_fee": "200.00"},
        )
        assert rejected_price_edit.status_code == 409, rejected_price_edit.text

        db = TestSessionLocal()
        db.info["tenant_id"] = tenant_id
        month_end = date(
            start.year, start.month, monthrange(start.year, start.month)[1]
        )
        db.add_all(
            [
                SubscriptionUsageCounter(
                    tenant_id=tenant_id,
                    metric="api_calls",
                    period_start=start,
                    used=500_000,
                ),
                SubscriptionUsageCounter(
                    tenant_id=tenant_id,
                    metric="verification_checks",
                    period_start=start,
                    used=25_000,
                ),
                SubscriptionUsageCounter(
                    tenant_id=tenant_id,
                    metric="ai_requests",
                    period_start=start,
                    used=8_000,
                ),
            ]
        )
        db.commit()
        db.close()

        generation_payload = {
            "tenant_id": str(tenant_id),
            "period_start": start.isoformat(),
            "period_end": month_end.isoformat(),
            "due_days": 30,
        }
        invoice_response = client.post(
            "/api/v1/billing/invoices/generate", json=generation_payload
        )
        assert invoice_response.status_code == 201, invoice_response.text
        invoice_data = invoice_response.json()["data"]
        assert Decimal(str(invoice_data["amount"])) == Decimal("5100.00")
        assert invoice_data["status"] == "DRAFT"
        assert len(invoice_data["line_items"]) == 4

        retry = client.post(
            "/api/v1/billing/invoices/generate", json=generation_payload
        )
        assert retry.status_code == 201, retry.text
        assert retry.json()["data"]["id"] == invoice_data["id"]

        issued = client.patch(
            f"/api/v1/billing/invoices/{invoice_data['id']}/status",
            params={"tenant_id": str(tenant_id)},
            json={"status": "ISSUED"},
        )
        assert issued.status_code == 200, issued.text
        paid = client.patch(
            f"/api/v1/billing/invoices/{invoice_data['id']}/status",
            params={"tenant_id": str(tenant_id)},
            json={"status": "PAID"},
        )
        assert paid.status_code == 200, paid.text
        assert paid.json()["data"]["status"] == "PAID"
    finally:
        # Delete data created by this test only, preserving shared tenants/counters.
        cleanup = TestSessionLocal()
        if tenant_id is not None:
            cleanup.info["tenant_id"] = tenant_id
            cleanup.query(InvoiceLineItem).filter(
                InvoiceLineItem.tenant_id == tenant_id
            ).delete(synchronize_session=False)
            cleanup.query(Invoice).filter(Invoice.tenant_id == tenant_id).delete(
                synchronize_session=False
            )
            cleanup.query(SubscriptionUsageCounter).filter(
                SubscriptionUsageCounter.tenant_id == tenant_id
            ).delete(synchronize_session=False)
            (
                cleanup.query(Subscription)
                .filter(Subscription.tenant_id == tenant_id)
                .delete(synchronize_session=False)
            )
            tenant_to_delete: Tenant | None = (
                cleanup.query(Tenant).filter(Tenant.id == tenant_id).first()
            )
            if tenant_to_delete is not None:
                cleanup.delete(tenant_to_delete)
        if plan_id is not None:
            plan = cleanup.query(BillingPlan).filter(BillingPlan.id == plan_id).first()
            if plan is not None:
                cleanup.delete(plan)
        else:
            plan = (
                cleanup.query(BillingPlan).filter(BillingPlan.name == plan_name).first()
            )
            if plan is not None:
                cleanup.delete(plan)
        cleanup.commit()
        cleanup.close()
