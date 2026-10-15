"""Integration coverage for subscription metering and quota enforcement."""

from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.tenant import Tenant
from app.services.subscription_service import (
    PLAN_CATALOG,
    SubscriptionService,
    ensure_subscription_capacity,
    record_subscription_usage,
)
from app.utils.date_time import utc_now
from app.utils.enums import SubscriptionStatus, TenantStatus


def test_catalog_defines_all_three_plans() -> None:
    assert set(PLAN_CATALOG) == {"starter", "professional", "enterprise"}
    assert PLAN_CATALOG["starter"]["usage_limits"]["max_users"] is not None
    assert PLAN_CATALOG["professional"]["features"]["advanced_reporting"] is True
    assert PLAN_CATALOG["enterprise"]["usage_limits"]["api_calls"] is None


def test_monthly_usage_limit_is_enforced(db_session: Session) -> None:
    tenant = Tenant(
        name="Subscription Test",
        code=f"SUB-{uuid4().hex[:12].upper()}",
        status=TenantStatus.ACTIVE,
    )
    db_session.add(tenant)
    db_session.commit()
    tenant_id = tenant.id
    today = utc_now().date()
    service = SubscriptionService(db_session)
    created = service.create(
        tenant_id=tenant_id,
        plan_name="starter",
        start_date=today,
        end_date=today + timedelta(days=30),
        status_value=SubscriptionStatus.ACTIVE,
        usage_limits={"api_calls": 1},
    )
    assert created.usage_limits["api_calls"] == 1

    try:
        record_subscription_usage(db_session, tenant_id, "api_calls")
        with pytest.raises(HTTPException) as exc_info:
            record_subscription_usage(db_session, tenant_id, "api_calls")
        assert exc_info.value.status_code == 429
        assert "api_calls" in str(exc_info.value.detail)
    finally:
        db_session.rollback()
        # Tenant foreign keys cascade to subscription and usage rows.
        db_session.info["tenant_id"] = tenant_id
        tenant_to_delete = db_session.scalar(
            select(Tenant)
            .where(Tenant.id == tenant_id)
            .execution_options(
                skip_tenant_filter=True,
                tenant_scope_reason="remove test-created subscription tenant",
            )
        )
        if tenant_to_delete is not None:
            db_session.delete(tenant_to_delete)
            db_session.commit()


@pytest.mark.parametrize(
    ("metric", "limit_key"),
    [("active_users", "max_users"), ("storage_bytes", "storage_bytes")],
)
def test_live_capacity_limits_are_enforced(
    db_session: Session, metric: str, limit_key: str
) -> None:
    tenant = Tenant(
        name="Capacity Test",
        code=f"CAP-{uuid4().hex[:12].upper()}",
        status=TenantStatus.ACTIVE,
    )
    db_session.add(tenant)
    db_session.commit()
    tenant_id = tenant.id
    today = utc_now().date()
    SubscriptionService(db_session).create(
        tenant_id=tenant_id,
        plan_name="starter",
        start_date=today,
        end_date=today + timedelta(days=30),
        status_value=SubscriptionStatus.ACTIVE,
        usage_limits={limit_key: 0},
    )

    try:
        with pytest.raises(HTTPException) as exc_info:
            ensure_subscription_capacity(db_session, tenant_id, metric, additional=1)
        headers = exc_info.value.headers
        assert exc_info.value.status_code == 429
        assert headers is not None
        assert headers["X-Subscription-Metric"] == metric
    finally:
        db_session.rollback()
        db_session.info["tenant_id"] = tenant_id
        tenant_to_delete = db_session.scalar(
            select(Tenant)
            .where(Tenant.id == tenant_id)
            .execution_options(
                skip_tenant_filter=True,
                tenant_scope_reason="remove test-created capacity subscription tenant",
            )
        )
        if tenant_to_delete is not None:
            db_session.delete(tenant_to_delete)
            db_session.commit()
