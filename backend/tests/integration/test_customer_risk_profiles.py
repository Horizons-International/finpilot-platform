import pytest

from app.models.audit_log import AuditLog
from app.utils.enums import AuditEventType, UserRole
from tests.helpers import (
    authenticate_client,
    create_customer_with_data,
)


def test_create_customer_risk_profile(
    client,
    create_test_user,
    cleanup_test_customers,
):
    admin = create_test_user(
        email="risk-profile-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    customer_response = create_customer_with_data(
        client,
        email="risk-profile-create@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    response = client.post(
        "/api/v1/customer-risk-profiles",
        json={
            "customer_id": customer_id,
            "risk_level": "MEDIUM",
            "risk_score": 45,
            "risk_category": "STANDARD",
            "assessed_at": "2026-09-10T10:00:00Z",
            "assessment_source": "INITIAL_ASSESSMENT",
        },
    )

    assert response.status_code == 201

    data = response.json()["data"]

    assert data["customer_id"] == customer_id
    assert data["risk_level"] == "MEDIUM"
    assert data["risk_score"] == 45
    assert data["risk_category"] == "STANDARD"
    assert data["assessment_source"] == "INITIAL_ASSESSMENT"


@pytest.mark.parametrize(
    "risk_level",
    [
        "LOW",
        "MEDIUM",
        "HIGH",
        "CRITICAL",
    ],
)
def test_create_customer_risk_profile_accepts_valid_risk_levels(
    client,
    create_test_user,
    cleanup_test_customers,
    risk_level,
):
    admin = create_test_user(
        email=f"risk-level-{risk_level.lower()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    customer_response = create_customer_with_data(
        client,
        email=f"risk-level-customer-{risk_level.lower()}@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    response = client.post(
        "/api/v1/customer-risk-profiles",
        json={
            "customer_id": customer_id,
            "risk_level": risk_level,
            "risk_score": 50,
            "risk_category": "STANDARD",
            "assessed_at": "2026-09-10T10:00:00Z",
            "assessment_source": "INITIAL_ASSESSMENT",
        },
    )

    assert response.status_code == 201
    assert response.json()["data"]["risk_level"] == risk_level


def test_get_customer_risk_profile(
    client,
    create_test_user,
    cleanup_test_customers,
):
    admin = create_test_user(
        email="risk-profile-get-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    customer_response = create_customer_with_data(
        client,
        email="risk-profile-get@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    create_response = client.post(
        "/api/v1/customer-risk-profiles",
        json={
            "customer_id": customer_id,
            "risk_level": "HIGH",
            "risk_score": 80,
            "risk_category": "ELEVATED",
            "assessed_at": "2026-09-10T10:00:00Z",
            "assessment_source": "INITIAL_ASSESSMENT",
        },
    )

    assert create_response.status_code == 201

    profile_id = create_response.json()["data"]["id"]

    response = client.get(
        f"/api/v1/customer-risk-profiles/customer/{customer_id}",
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["id"] == profile_id
    assert data["customer_id"] == customer_id
    assert data["risk_level"] == "HIGH"
    assert data["risk_score"] == 80


def test_get_customer_risk_profile_by_id(
    client,
    create_test_user,
    cleanup_test_customers,
):
    admin = create_test_user(
        email="risk-profile-id-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    customer_response = create_customer_with_data(
        client,
        email="risk-profile-id@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    create_response = client.post(
        "/api/v1/customer-risk-profiles",
        json={
            "customer_id": customer_id,
            "risk_level": "LOW",
            "risk_score": 10,
            "risk_category": "LOW_RISK",
            "assessed_at": "2026-09-10T10:00:00Z",
            "assessment_source": "INITIAL_ASSESSMENT",
        },
    )

    assert create_response.status_code == 201

    profile_id = create_response.json()["data"]["id"]

    response = client.get(
        f"/api/v1/customer-risk-profiles/{profile_id}",
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["id"] == profile_id
    assert data["customer_id"] == customer_id
    assert data["risk_level"] == "LOW"


def test_customer_can_have_only_one_risk_profile(
    client,
    create_test_user,
    cleanup_test_customers,
):
    admin = create_test_user(
        email="risk-profile-duplicate-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    customer_response = create_customer_with_data(
        client,
        email="risk-profile-duplicate@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    payload = {
        "customer_id": customer_id,
        "risk_level": "MEDIUM",
        "risk_score": 40,
        "risk_category": "STANDARD",
        "assessed_at": "2026-09-10T10:00:00Z",
        "assessment_source": "INITIAL_ASSESSMENT",
    }

    first_response = client.post(
        "/api/v1/customer-risk-profiles",
        json=payload,
    )

    assert first_response.status_code == 201

    second_response = client.post(
        "/api/v1/customer-risk-profiles",
        json=payload,
    )

    assert second_response.status_code == 400

    data = second_response.json()

    assert data["success"] is False


def test_create_risk_profile_for_nonexistent_customer_returns_404(
    client,
    create_test_user,
):
    admin = create_test_user(
        email="risk-profile-missing-customer@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    response = client.post(
        "/api/v1/customer-risk-profiles",
        json={
            "customer_id": "00000000-0000-0000-0000-000000000000",
            "risk_level": "HIGH",
            "risk_score": 80,
            "risk_category": "ELEVATED",
            "assessed_at": "2026-09-10T10:00:00Z",
            "assessment_source": "INITIAL_ASSESSMENT",
        },
    )

    assert response.status_code == 404

    data = response.json()

    assert data["success"] is False


def test_invalid_risk_level_is_rejected(
    client,
    create_test_user,
    cleanup_test_customers,
):
    admin = create_test_user(
        email="risk-profile-invalid-level@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    customer_response = create_customer_with_data(
        client,
        email="risk-profile-invalid-level-customer@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    response = client.post(
        "/api/v1/customer-risk-profiles",
        json={
            "customer_id": customer_id,
            "risk_level": "EXTREME",
            "risk_score": 99,
            "risk_category": "UNKNOWN",
            "assessed_at": "2026-09-10T10:00:00Z",
            "assessment_source": "INITIAL_ASSESSMENT",
        },
    )

    assert response.status_code == 422


def test_get_missing_customer_risk_profile_returns_404(
    client,
    create_test_user,
    cleanup_test_customers,
):
    admin = create_test_user(
        email="risk-profile-not-found@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    customer_response = create_customer_with_data(
        client,
        email="risk-profile-not-found-customer@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    response = client.get(
        f"/api/v1/customer-risk-profiles/customer/{customer_id}",
    )

    assert response.status_code == 404

    data = response.json()

    assert data["success"] is False


def test_customer_risk_profile_creation_is_audited(
    client,
    create_test_user,
    cleanup_test_customers,
    db_session,
):
    admin = create_test_user(
        email="risk-profile-audit@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    customer_response = create_customer_with_data(
        client,
        email="risk-profile-audit-customer@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    response = client.post(
        "/api/v1/customer-risk-profiles",
        json={
            "customer_id": customer_id,
            "risk_level": "HIGH",
            "risk_score": 75,
            "risk_category": "ELEVATED",
            "assessed_at": "2026-09-10T10:00:00Z",
            "assessment_source": "INITIAL_ASSESSMENT",
        },
    )

    assert response.status_code == 201

    profile_id = response.json()["data"]["id"]

    audit_log = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.user_id == admin.id,
            AuditLog.event_type == AuditEventType.CUSTOMER_RISK_PROFILE_CREATED,
            AuditLog.resource_type == "customer_risk_profile",
        )
        .order_by(AuditLog.timestamp.desc())
        .first()
    )

    assert audit_log is not None
    assert audit_log.resource_id is not None
    assert str(audit_log.resource_id) == profile_id
