"""Regression tests for the async partner-onboarding read endpoints."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.models.audit_log import AuditLog
from app.models.partner_onboarding import PartnerOnboarding, PartnerOnboardingHistory
from app.utils.enums import UserRole
from tests.helpers import authenticate_client


def _payload() -> dict[str, object]:
    return {
        "organization_name": f"Async Read Bank {uuid4().hex[:8]}",
        "legal_name": "Async Read Bank Limited",
        "registration_number": f"REG-{uuid4().hex[:10].upper()}",
        "tax_identification_number": "TAX-ASYNC-123",
        "industry": "Financial Services",
        "business_description": "A prospective regulated financial institution.",
        "contact_name": "Partner Contact",
        "contact_email": f"async-partner-{uuid4()}@example.com",
        "contact_phone": "+249912345678",
        "website": "https://partner.example",
        "country": "SD",
    }


@pytest.fixture
def cleanup_async_read_onboarding(db_session):
    existing_ids = {item.id for item in db_session.query(PartnerOnboarding.id).all()}
    yield
    db_session.expire_all()

    created_ids = [
        onboarding_id
        for (onboarding_id,) in db_session.query(PartnerOnboarding.id).all()
        if onboarding_id not in existing_ids
    ]
    if created_ids:
        db_session.query(AuditLog).filter(
            AuditLog.resource_type == "partner_onboarding",
            AuditLog.resource_id.in_(created_ids),
        ).delete(synchronize_session=False)
        db_session.query(PartnerOnboardingHistory).filter(
            PartnerOnboardingHistory.onboarding_id.in_(created_ids)
        ).delete(synchronize_session=False)
        db_session.query(PartnerOnboarding).filter(
            PartnerOnboarding.id.in_(created_ids)
        ).delete(synchronize_session=False)
    db_session.commit()


def _create_request(client: TestClient) -> dict[str, object]:
    response = client.post("/api/v1/partner-onboarding", json=_payload())
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert isinstance(data, dict)
    return data


def test_async_platform_admin_read_endpoints(
    client: TestClient,
    create_test_user,
    cleanup_async_read_onboarding,
):
    onboarding = _create_request(client)
    onboarding_id = onboarding["id"]

    admin = create_test_user(
        UserRole.ADMINISTRATOR,
        f"async-onboarding-admin-{uuid4()}@example.com",
        is_platform_admin=True,
    )
    authenticate_client(client, admin)

    list_response = client.get(
        "/api/v1/partner-onboarding",
        params={"status": "REQUESTED"},
    )
    assert list_response.status_code == 200, list_response.text
    assert any(item["id"] == onboarding_id for item in list_response.json()["data"])

    detail_response = client.get(f"/api/v1/partner-onboarding/{onboarding_id}")
    assert detail_response.status_code == 200, detail_response.text
    assert detail_response.json()["data"]["id"] == onboarding_id

    progress_response = client.get(
        f"/api/v1/partner-onboarding/{onboarding_id}/progress"
    )
    assert progress_response.status_code == 200, progress_response.text
    assert progress_response.json()["data"]["onboarding_id"] == onboarding_id

    history_response = client.get(f"/api/v1/partner-onboarding/{onboarding_id}/history")
    assert history_response.status_code == 200, history_response.text
    assert [item["action"] for item in history_response.json()["data"]] == ["REQUESTED"]

    documents_response = client.get(
        f"/api/v1/partner-onboarding/{onboarding_id}/documents"
    )
    assert documents_response.status_code == 200, documents_response.text
    assert documents_response.json()["data"] == []


def test_async_customer_portal_progress_requires_valid_token(
    client: TestClient,
    cleanup_async_read_onboarding,
):
    create_response = client.post(
        "/api/v1/partner-onboarding/portal",
        json=_payload(),
    )
    assert create_response.status_code == 201, create_response.text
    data = create_response.json()["data"]
    onboarding_id = data["id"]
    portal_token = data["portal_token"]

    progress_response = client.get(
        f"/api/v1/partner-onboarding/portal/{onboarding_id}/progress",
        headers={"X-Onboarding-Token": portal_token},
    )
    assert progress_response.status_code == 200, progress_response.text
    assert progress_response.json()["data"]["onboarding_id"] == onboarding_id

    invalid_token_response = client.get(
        f"/api/v1/partner-onboarding/portal/{onboarding_id}/progress",
        headers={"X-Onboarding-Token": "invalid-token"},
    )
    assert invalid_token_response.status_code == 404
