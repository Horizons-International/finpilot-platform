from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.schemas.billing import BillingPlanCreate, InvoiceGenerateRequest


def test_monthly_subscription_plan_accepts_base_fee() -> None:
    plan = BillingPlanCreate(
        name="Professional Monthly",
        pricing_model="SUBSCRIPTION",
        billing_interval="MONTHLY",
        subscription_tier="professional",
        base_fee=Decimal("2500.00"),
    )

    assert plan.base_fee == Decimal("2500.00")
    assert plan.billing_interval == "MONTHLY"


def test_usage_plan_requires_rates_and_monthly_interval() -> None:
    with pytest.raises(ValidationError, match="require at least one unit rate"):
        BillingPlanCreate(
            name="Missing rates",
            pricing_model="USAGE_BASED",
            billing_interval="MONTHLY",
        )

    with pytest.raises(ValidationError, match="bill monthly"):
        BillingPlanCreate(
            name="Annual metered",
            pricing_model="USAGE_BASED",
            billing_interval="ANNUAL",
            unit_rates={"api_calls": Decimal("0.001")},
        )


def test_plan_rejects_unsupported_limits_and_negative_rates() -> None:
    with pytest.raises(ValidationError, match="Unsupported limit keys"):
        BillingPlanCreate(
            name="Invalid limit",
            pricing_model="SUBSCRIPTION",
            billing_interval="MONTHLY",
            base_fee=Decimal("1.00"),
            limits={"made_up_limit": 3},
        )

    with pytest.raises(ValidationError):
        BillingPlanCreate(
            name="Negative rate",
            pricing_model="USAGE_BASED",
            billing_interval="MONTHLY",
            unit_rates={"api_calls": Decimal("-0.001")},
        )


def test_invoice_period_must_align_to_full_calendar_months() -> None:
    request = InvoiceGenerateRequest(
        tenant_id=UUID("db5aa3e3-8d54-42d8-9a01-cb890ccad8b2"),
        period_start=date(2026, 10, 1),
        period_end=date(2026, 10, 31),
    )
    assert request.period_start == date(2026, 10, 1)

    with pytest.raises(ValidationError, match="last day of a calendar month"):
        InvoiceGenerateRequest(
            tenant_id=UUID("db5aa3e3-8d54-42d8-9a01-cb890ccad8b2"),
            period_start=date(2026, 10, 1),
            period_end=date(2026, 10, 30),
        )
