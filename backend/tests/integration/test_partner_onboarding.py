"""Integration tests for the partner onboarding workflow."""

from typing import Any, cast
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.models.audit_log import AuditLog
from app.models.organization import Organization
from app.models.partner_onboarding import (
    PartnerOnboarding,
    PartnerOnboardingHistory,
)
from app.models.tenant import Tenant
from app.utils.enums import PartnerOnboardingStatus, UserRole
from tests.helpers import authenticate_client


def _payload(email: str | None = None) -> dict[str, object]:
    return {
        "organization_name": f"Partner Bank {uuid4().hex[:6]}",
        "legal_name": "Partner Bank Limited",
        "registration_number": f"REG-{uuid4().hex[:10].upper()}",
        "tax_identification_number": "TAX-12345",
        "industry": "Financial Services",
        "business_description": "A prospective regulated financial institution.",
        "contact_name": "Partner Contact",
        "contact_email": email or f"partner-{uuid4()}@example.com",
        "contact_phone": "+249912345678",
        "website": "https://partner.example",
        "country": "SD",
    }


@pytest.fixture
def cleanup_partner_onboarding(db_session):
    existing_onboarding_ids = {
        item.id for item in db_session.query(PartnerOnboarding).all()
    }
    existing_tenant_ids = {item.id for item in db_session.query(Tenant).all()}
    yield
    db_session.expire_all()

    created_requests = [
        item
        for item in db_session.query(PartnerOnboarding).all()
        if item.id not in existing_onboarding_ids
    ]
    created_request_ids = {item.id for item in created_requests}
    activated_tenant_ids = {
        item.activated_tenant_id
        for item in created_requests
        if item.activated_tenant_id is not None
        and item.activated_tenant_id not in existing_tenant_ids
    }

    if created_request_ids:
        db_session.query(AuditLog).filter(
            AuditLog.resource_type == "partner_onboarding",
            AuditLog.resource_id.in_(created_request_ids),
        ).delete(synchronize_session=False)
        db_session.query(PartnerOnboardingHistory).filter(
            PartnerOnboardingHistory.onboarding_id.in_(created_request_ids)
        ).delete(synchronize_session=False)
        db_session.query(PartnerOnboarding).filter(
            PartnerOnboarding.id.in_(created_request_ids)
        ).delete(synchronize_session=False)

    if activated_tenant_ids:
        db_session.query(Organization).filter(
            Organization.tenant_id.in_(activated_tenant_ids)
        ).delete(synchronize_session=False)
        db_session.query(Tenant).filter(Tenant.id.in_(activated_tenant_ids)).delete(
            synchronize_session=False
        )

    db_session.commit()


def _create_request(
    client: TestClient,
    email: str | None = None,
) -> dict[str, Any]:
    response = client.post(
        "/api/v1/partner-onboarding",
        json=_payload(email),
    )

    assert response.status_code == 201, response.text

    return cast(dict[str, Any], response.json()["data"])


def test_public_partner_can_submit_request_and_admin_can_view_history(
    client: TestClient,
    create_test_user,
    cleanup_partner_onboarding,
):
    item = _create_request(client)
    assert item["status"] == PartnerOnboardingStatus.REQUESTED.value
    assert item["assigned_to"] is None
    assert item["activated_tenant_id"] is None

    admin = create_test_user(
        UserRole.ADMINISTRATOR,
        f"partner-onboarding-admin-{uuid4()}@example.com",
        is_platform_admin=True,
    )
    authenticate_client(client, admin)

    response = client.get(f"/api/v1/partner-onboarding/{item['id']}/history")
    assert response.status_code == 200, response.text
    history = response.json()["data"]
    assert len(history) == 1
    assert history[0]["action"] == "REQUESTED"
    assert history[0]["status"] == "REQUESTED"


def test_reviewer_can_progress_request_and_approval_activates_tenant(
    client: TestClient,
    create_test_user,
    cleanup_partner_onboarding,
    db_session,
):
    item = _create_request(client)
    admin = create_test_user(
        UserRole.ADMINISTRATOR,
        f"partner-onboarding-owner-{uuid4()}@example.com",
        is_platform_admin=True,
    )
    reviewer = create_test_user(
        UserRole.COMPLIANCE_OFFICER,
        f"partner-onboarding-reviewer-{uuid4()}@example.com",
        is_platform_admin=True,
    )
    authenticate_client(client, admin)

    response = client.patch(
        f"/api/v1/partner-onboarding/{item['id']}/assignment",
        json={"assigned_to": str(reviewer.id)},
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["assigned_to"] == str(reviewer.id)

    expected_statuses = [
        PartnerOnboardingStatus.BUSINESS_INFORMATION.value,
        PartnerOnboardingStatus.COMPLIANCE_REVIEW.value,
        PartnerOnboardingStatus.TECHNICAL_SETUP.value,
        PartnerOnboardingStatus.API_CREDENTIALS.value,
    ]
    for expected_status in expected_statuses:
        response = client.post(
            f"/api/v1/partner-onboarding/{item['id']}/advance",
            json={"notes": f"Completed {expected_status.lower()} checks."},
        )
        assert response.status_code == 200, response.text
        assert response.json()["data"]["status"] == expected_status

    response = client.post(
        f"/api/v1/partner-onboarding/{item['id']}/approve",
        json={"notes": "Compliance and technical checks passed."},
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["status"] == PartnerOnboardingStatus.ACTIVE.value
    assert data["activated_tenant_id"]
    assert data["activated_at"]

    tenant_id = data["activated_tenant_id"]
    db_session.expire_all()
    tenant = db_session.query(Tenant).filter(Tenant.id == tenant_id).first()
    organization = (
        db_session.query(Organization)
        .filter(Organization.tenant_id == tenant_id)
        .first()
    )
    assert tenant is not None
    assert tenant.status.value == "ACTIVE"
    assert organization is not None
    assert organization.status.value == "ACTIVE"
    assert organization.name == data["organization_name"]
    assert organization.country == data["country"]

    history_response = client.get(f"/api/v1/partner-onboarding/{item['id']}/history")
    assert history_response.status_code == 200, history_response.text
    actions = [record["action"] for record in history_response.json()["data"]]
    assert "ASSIGNED" in actions
    assert actions.count("STAGE_CHANGED") == 4
    assert "APPROVED_AND_ACTIVATED" in actions


def test_reviewer_must_be_a_platform_admin_and_stages_cannot_be_skipped(
    client: TestClient,
    create_test_user,
    cleanup_partner_onboarding,
):
    item = _create_request(client)
    admin = create_test_user(
        UserRole.ADMINISTRATOR,
        f"partner-onboarding-admin-{uuid4()}@example.com",
        is_platform_admin=True,
    )
    ordinary_user = create_test_user(
        UserRole.ADMINISTRATOR,
        f"partner-onboarding-non-platform-{uuid4()}@example.com",
        is_platform_admin=False,
    )
    authenticate_client(client, admin)

    response = client.post(
        f"/api/v1/partner-onboarding/{item['id']}/advance",
        json={},
    )
    assert response.status_code == 409

    response = client.patch(
        f"/api/v1/partner-onboarding/{item['id']}/assignment",
        json={"assigned_to": str(ordinary_user.id)},
    )
    assert response.status_code == 400

    response = client.post(
        f"/api/v1/partner-onboarding/{item['id']}/approve",
        json={},
    )
    assert response.status_code == 409


def test_non_platform_administrator_cannot_read_onboarding_queue(
    client: TestClient,
    create_test_user,
    cleanup_partner_onboarding,
):
    _create_request(client)
    tenant_admin = create_test_user(
        UserRole.ADMINISTRATOR,
        f"partner-onboarding-tenant-admin-{uuid4()}@example.com",
        is_platform_admin=False,
    )
    authenticate_client(client, tenant_admin)

    response = client.get("/api/v1/partner-onboarding")
    assert response.status_code == 403


def test_partner_request_can_be_rejected_and_cannot_be_reopened(
    client: TestClient,
    create_test_user,
    cleanup_partner_onboarding,
):
    item = _create_request(client)
    admin = create_test_user(
        UserRole.ADMINISTRATOR,
        f"partner-onboarding-reject-{uuid4()}@example.com",
        is_platform_admin=True,
    )
    authenticate_client(client, admin)

    response = client.post(
        f"/api/v1/partner-onboarding/{item['id']}/reject",
        json={"reason": "Required regulatory documents were not supplied."},
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["status"] == PartnerOnboardingStatus.REJECTED.value
    assert "regulatory documents" in data["rejection_reason"]

    response = client.post(
        f"/api/v1/partner-onboarding/{item['id']}/advance",
        json={},
    )
    assert response.status_code == 409


def test_duplicate_open_request_for_contact_email_is_rejected(
    client: TestClient,
    cleanup_partner_onboarding,
):
    email = f"duplicate-partner-{uuid4()}@example.com"
    _create_request(client, email)

    response = client.post(
        "/api/v1/partner-onboarding",
        json=_payload(email),
    )
    assert response.status_code == 409, response.text
