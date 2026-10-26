"""Integration tests for the tenant-scoped product usage analytics API."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.models.audit_log import AuditLog
from app.models.security_event import SecurityEvent
from app.utils.enums import AuditEventType, UserRole
from tests.conftest import TestSessionLocal
from tests.helpers import authenticate_client


def _insert_event_rows(tenant_id, user_id):
    now = datetime.now(timezone.utc)
    recent = SecurityEvent(
        tenant_id=tenant_id,
        user_id=user_id,
        event_type="API_ACCESS",
        request_path="/api/v1/customers",
        timestamp=now - timedelta(minutes=2),
        details={"method": "GET", "response_status": 200},
    )
    old = SecurityEvent(
        tenant_id=tenant_id,
        user_id=user_id,
        event_type="API_ACCESS",
        request_path="/api/v1/workflows",
        timestamp=now - timedelta(days=4),
        details={"method": "GET", "response_status": 200},
    )
    login = AuditLog(
        tenant_id=tenant_id,
        user_id=user_id,
        email=f"analytics-{uuid4().hex}@example.com",
        event_type=AuditEventType.LOGIN_SUCCESS,
        timestamp=now - timedelta(minutes=3),
        resource_type="user",
    )
    db = TestSessionLocal()
    db.info["tenant_id"] = tenant_id
    try:
        db.add_all([recent, old, login])
        db.commit()
        return now.date(), [recent.id, old.id], login.id
    finally:
        db.close()


def _delete_event_rows(tenant_id, event_ids, login_id):
    db = TestSessionLocal()
    db.info["tenant_id"] = tenant_id
    try:
        db.query(SecurityEvent).filter(SecurityEvent.id.in_(event_ids)).delete(
            synchronize_session=False
        )
        db.query(AuditLog).filter(AuditLog.id == login_id).delete(
            synchronize_session=False
        )
        db.commit()
    finally:
        db.close()


def test_dashboard_filters_by_date_and_reports_feature_usage(client, create_test_user):
    user = create_test_user(
        role=UserRole.ADMINISTRATOR.value,
        email=f"product-usage-{uuid4().hex}@example.com",
    )
    today, event_ids, login_id = _insert_event_rows(user.tenant_id, user.id)
    try:
        authenticate_client(client, user)
        response = client.get(
            "/api/v1/product-analytics/dashboard",
            params={"start_date": today.isoformat(), "end_date": today.isoformat()},
        )
        assert response.status_code == 200, response.text
        payload = response.json()["data"]
        assert payload["total_customers"] == 1
        assert payload["customers"][0]["tenant_id"] == str(user.tenant_id)
        assert payload["customers"][0]["api_calls"] == 1
        assert payload["customers"][0]["active_users"] == 1
        assert (
            next(
                feature
                for feature in payload["customers"][0]["features"]
                if feature["feature_key"] == "customer_management"
            )["request_count"]
            == 1
        )
        assert (
            "Workflows and task automation"
            in payload["customers"][0]["unused_features"]
        )

        report = client.get(
            "/api/v1/product-analytics/features",
            params={"start_date": today.isoformat(), "end_date": today.isoformat()},
        )
        assert report.status_code == 200, report.text
        customer_feature = next(
            feature
            for feature in report.json()["data"]["features"]
            if feature["feature_key"] == "customer_management"
        )
        assert customer_feature["request_count"] == 1
    finally:
        _delete_event_rows(user.tenant_id, event_ids, login_id)


def test_non_product_manager_cannot_filter_to_another_tenant(client, create_test_user):
    user = create_test_user(
        role=UserRole.ADMINISTRATOR.value,
        email=f"product-usage-scope-{uuid4().hex}@example.com",
    )
    authenticate_client(client, user)
    response = client.get(
        "/api/v1/product-analytics/dashboard",
        params={"tenant_id": str(uuid4())},
    )
    assert response.status_code == 403, response.text


def test_product_manager_can_query_tenant_level_dashboard(client, create_test_user):
    user = create_test_user(
        role=UserRole.PRODUCT_MANAGER.value,
        email=f"product-manager-{uuid4().hex}@example.com",
        is_platform_admin=True,
    )
    authenticate_client(client, user)
    response = client.get(
        "/api/v1/product-analytics/dashboard",
        params={
            "start_date": (
                datetime.now(timezone.utc).date() - timedelta(days=1)
            ).isoformat(),
            "end_date": datetime.now(timezone.utc).date().isoformat(),
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["total_customers"] >= 1
