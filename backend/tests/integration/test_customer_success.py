"""Integration tests for customer-success lifecycle, usage and support history."""

from datetime import date, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.models.customer_success import (
    CustomerSuccessHistory,
    CustomerSuccessProfile,
    CustomerSuccessSupportInteraction,
    CustomerSuccessUsageSnapshot,
)
from app.models.subscription import Subscription, SubscriptionUsageCounter
from app.models.tenant import Tenant
from app.utils.enums import SubscriptionStatus, TenantStatus, UserRole
from tests.conftest import TestSessionLocal
from tests.helpers import authenticate_client


@pytest.fixture
def cleanup_customer_success():
    db = TestSessionLocal()
    try:
        existing_profiles = set(db.scalars(select(CustomerSuccessProfile.id)).all())
        existing_tenants = set(db.scalars(select(Tenant.id)).all())
    finally:
        db.close()

    yield

    db = TestSessionLocal()
    try:
        created_profiles = (
            set(db.scalars(select(CustomerSuccessProfile.id)).all()) - existing_profiles
        )
        if created_profiles:
            db.query(CustomerSuccessHistory).filter(
                CustomerSuccessHistory.profile_id.in_(created_profiles)
            ).delete(synchronize_session=False)
            db.query(CustomerSuccessSupportInteraction).filter(
                CustomerSuccessSupportInteraction.profile_id.in_(created_profiles)
            ).delete(synchronize_session=False)
            db.query(CustomerSuccessUsageSnapshot).filter(
                CustomerSuccessUsageSnapshot.profile_id.in_(created_profiles)
            ).delete(synchronize_session=False)
            db.query(CustomerSuccessProfile).filter(
                CustomerSuccessProfile.id.in_(created_profiles)
            ).delete(synchronize_session=False)
        created_tenants = set(db.scalars(select(Tenant.id)).all()) - existing_tenants
        if created_tenants:
            db.query(Tenant).filter(Tenant.id.in_(created_tenants)).delete(
                synchronize_session=False
            )
        db.commit()
    finally:
        db.close()


def _create_customer_tenant() -> Tenant:
    db = TestSessionLocal()
    try:
        tenant = Tenant(
            name="Customer Success Test Bank",
            code=f"CS-{uuid4().hex[:12]}",
            status=TenantStatus.ACTIVE,
        )
        db.add(tenant)
        db.commit()
        db.refresh(tenant)
        return tenant
    finally:
        db.close()


def test_customer_success_lifecycle_usage_and_support(
    client, create_test_user, cleanup_customer_success
):
    manager = create_test_user(
        email=f"customer-success-manager-{uuid4().hex[:8]}@example.com",
        role=UserRole.CUSTOMER_SUCCESS_MANAGER,
    )
    authenticate_client(client, manager)
    customer_tenant = _create_customer_tenant()

    create_response = client.post(
        "/api/v1/customer-success",
        json={
            "customer_tenant_id": str(customer_tenant.id),
            "account_status": "TRIAL",
            "implementation_stage": "NOT_STARTED",
            "assigned_manager_id": str(manager.id),
        },
    )
    assert create_response.status_code == 201, create_response.text
    profile = create_response.json()["data"]
    profile_id = profile["id"]
    assert profile["customer_tenant_name"] == customer_tenant.name
    assert profile["health_score"] <= 100

    update_response = client.patch(
        f"/api/v1/customer-success/{profile_id}",
        json={
            "account_status": "ACTIVE",
            "implementation_stage": "LIVE",
            "last_contacted_at": "2026-10-25T09:00:00Z",
        },
    )
    assert update_response.status_code == 200, update_response.text

    usage_response = client.post(
        f"/api/v1/customer-success/{profile_id}/usage-snapshots",
        json={
            "period_start": "2026-10-01",
            "period_end": "2026-10-31",
            "active_users": 0,
            "licensed_users": 10,
            "api_calls": 0,
            "api_call_limit": 100,
            "active_features": 2,
            "available_features": 4,
            "source": "MANUAL",
        },
    )
    assert usage_response.status_code == 201, usage_response.text

    support_response = client.post(
        f"/api/v1/customer-success/{profile_id}/support-interactions",
        json={
            "subject": "Production integration blocked",
            "description": "The test account cannot complete the integration flow.",
            "category": "INTEGRATION",
            "severity": "CRITICAL",
            "status": "OPEN",
            "assigned_to": str(manager.id),
        },
    )
    assert support_response.status_code == 201, support_response.text

    refreshed = client.get(f"/api/v1/customer-success/{profile_id}")
    assert refreshed.status_code == 200, refreshed.text
    current = refreshed.json()["data"]
    assert current["account_status"] == "ACTIVE"
    assert current["implementation_stage"] == "LIVE"
    assert current["health_score"] < 60
    assert current["health_band"] == "AT_RISK"

    history = client.get(f"/api/v1/customer-success/{profile_id}/history")
    assert history.status_code == 200, history.text
    event_types = {item["event_type"] for item in history.json()["data"]}
    assert "PROFILE_CREATED" in event_types
    assert "ACCOUNT_STATUS_CHANGED" in event_types
    assert "USAGE_SNAPSHOT_RECORDED" in event_types
    assert "SUPPORT_INTERACTION_CREATED" in event_types


def test_customer_success_can_import_linked_subscription_usage(
    client, create_test_user, cleanup_customer_success
):
    manager = create_test_user(
        email=f"customer-success-usage-{uuid4().hex[:8]}@example.com",
        role=UserRole.CUSTOMER_SUCCESS_MANAGER,
    )
    authenticate_client(client, manager)
    customer_tenant = _create_customer_tenant()
    today = date.today()
    period_start = today.replace(day=1)

    db = TestSessionLocal()
    try:
        db.add(
            Subscription(
                tenant_id=customer_tenant.id,
                plan_name="STARTER",
                status=SubscriptionStatus.ACTIVE,
                start_date=today,
                end_date=today + timedelta(days=365),
                usage_limits={"max_users": 20, "api_calls": 1000},
                features={"advanced_reporting": False},
            )
        )
        db.add(
            SubscriptionUsageCounter(
                tenant_id=customer_tenant.id,
                metric="api_calls",
                period_start=period_start,
                used=123,
            )
        )
        db.commit()
    finally:
        db.close()

    created = client.post(
        "/api/v1/customer-success",
        json={
            "customer_tenant_id": str(customer_tenant.id),
            "implementation_stage": "LIVE",
        },
    )
    assert created.status_code == 201, created.text
    profile_id = created.json()["data"]["id"]

    imported = client.post(
        f"/api/v1/customer-success/{profile_id}/usage-snapshots/from-subscription"
    )
    assert imported.status_code == 201, imported.text
    snapshot = imported.json()["data"]
    assert snapshot["source"] == "SUBSCRIPTION_IMPORT"
    assert snapshot["api_calls"] == 123
    assert snapshot["api_call_limit"] == 1000
    assert snapshot["licensed_users"] == 20


def test_customer_success_profiles_are_tenant_scoped(
    client, create_test_user, cleanup_customer_success
):
    from fastapi import HTTPException

    from app.services.customer_success_service import CustomerSuccessService

    owner = create_test_user(
        email=f"customer-success-owner-{uuid4().hex[:8]}@example.com",
        role=UserRole.CUSTOMER_SUCCESS_MANAGER,
    )
    authenticate_client(client, owner)
    customer_tenant = _create_customer_tenant()
    created = client.post(
        "/api/v1/customer-success",
        json={"customer_tenant_id": str(customer_tenant.id)},
    )
    assert created.status_code == 201, created.text
    profile_id = UUID(created.json()["data"]["id"])

    # Query the same profile through an independent team's tenant-bound session.
    other_owner_tenant = _create_customer_tenant()
    db = TestSessionLocal()
    try:
        db.info["tenant_id"] = other_owner_tenant.id
        service = CustomerSuccessService(db, other_owner_tenant.id)
        with pytest.raises(HTTPException) as exc_info:
            service.get_profile(profile_id)
        assert exc_info.value.status_code == 404
    finally:
        db.close()
