"""Integration tests for the self-service enterprise onboarding portal."""

import hashlib
from typing import Any, cast
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.models.api_key import APIKey
from app.models.audit_log import AuditLog
from app.models.organization import Organization
from app.models.partner_onboarding import (
    PartnerOnboarding,
    PartnerOnboardingAdministrator,
    PartnerOnboardingDocument,
    PartnerOnboardingHistory,
)
from app.models.tenant import Tenant
from app.models.user_invitation import UserInvitation
from app.utils.enums import PartnerOnboardingStatus, UserRole
from tests.helpers import authenticate_client


def _portal_payload() -> dict[str, object]:
    suffix = uuid4().hex[:10]
    return {
        "organization_name": f"Portal Bank {suffix}",
        "legal_name": f"Portal Bank {suffix} Ltd",
        "registration_number": f"REG-{suffix.upper()}",
        "tax_identification_number": f"TAX-{suffix.upper()}",
        "industry": "Financial Services",
        "business_description": "A prospective regulated financial institution.",
        "contact_name": "Bank Integration Contact",
        "contact_email": f"portal-{suffix}@example.com",
        "contact_phone": "+249912345678",
        "website": "https://bank.example.com",
        "country": "SD",
    }


@pytest.fixture
def cleanup_portal_onboarding(db_session):
    existing_onboarding_ids = {
        item.id for item in db_session.query(PartnerOnboarding).all()
    }
    existing_tenant_ids = {item.id for item in db_session.query(Tenant).all()}
    yield
    db_session.expire_all()

    created = [
        item
        for item in db_session.query(PartnerOnboarding).all()
        if item.id not in existing_onboarding_ids
    ]
    onboarding_ids = {item.id for item in created}
    tenant_ids = {
        item.activated_tenant_id
        for item in created
        if item.activated_tenant_id is not None
        and item.activated_tenant_id not in existing_tenant_ids
    }
    document_ids = {
        item.id
        for item in db_session.query(PartnerOnboardingDocument).all()
        if item.onboarding_id in onboarding_ids
    }
    api_key_ids = {
        item.id
        for item in db_session.query(APIKey).all()
        if item.tenant_id in tenant_ids
    }

    if onboarding_ids:
        db_session.query(AuditLog).filter(
            AuditLog.resource_type.in_(
                ["partner_onboarding", "partner_onboarding_document"]
            ),
            AuditLog.resource_id.in_(onboarding_ids | document_ids),
        ).delete(synchronize_session=False)
        db_session.query(PartnerOnboardingHistory).filter(
            PartnerOnboardingHistory.onboarding_id.in_(onboarding_ids)
        ).delete(synchronize_session=False)
        db_session.query(PartnerOnboardingDocument).filter(
            PartnerOnboardingDocument.onboarding_id.in_(onboarding_ids)
        ).delete(synchronize_session=False)
        db_session.query(PartnerOnboardingAdministrator).filter(
            PartnerOnboardingAdministrator.onboarding_id.in_(onboarding_ids)
        ).delete(synchronize_session=False)
        db_session.query(PartnerOnboarding).filter(
            PartnerOnboarding.id.in_(onboarding_ids)
        ).delete(synchronize_session=False)

    if tenant_ids:
        db_session.query(AuditLog).filter(
            AuditLog.resource_type == "api_key",
            AuditLog.resource_id.in_(api_key_ids),
        ).delete(synchronize_session=False)
        db_session.query(Organization).filter(
            Organization.tenant_id.in_(tenant_ids)
        ).delete(synchronize_session=False)
        db_session.query(UserInvitation).filter(
            UserInvitation.tenant_id.in_(tenant_ids)
        ).delete(synchronize_session=False)
        db_session.query(APIKey).filter(APIKey.tenant_id.in_(tenant_ids)).delete(
            synchronize_session=False
        )
        db_session.query(Tenant).filter(Tenant.id.in_(tenant_ids)).delete(
            synchronize_session=False
        )

    db_session.commit()


def _upload_required_document(
    client: TestClient,
    *,
    onboarding_id: str,
    token: str,
    document_type: str,
) -> dict[str, Any]:
    response = client.post(
        f"/api/v1/partner-onboarding/portal/{onboarding_id}/documents",
        headers={"X-Onboarding-Token": token},
        data={"document_type": document_type},
        files={
            "file": (
                f"{document_type}.pdf",
                b"%PDF-1.4\nFinPilot onboarding test evidence\n%%EOF\n",
                "application/pdf",
            )
        },
    )
    assert response.status_code == 201, response.text
    return cast(dict[str, Any], response.json()["data"])


def test_portal_enforces_required_steps_and_activates_enterprise(
    client: TestClient,
    create_test_user,
    cleanup_portal_onboarding,
    db_session,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(settings, "STORAGE_PATH", str(tmp_path))
    create_response = client.post(
        "/api/v1/partner-onboarding/portal",
        json=_portal_payload(),
    )
    assert create_response.status_code == 201, create_response.text
    created = create_response.json()["data"]
    onboarding_id = created["id"]
    portal_token = created["portal_token"]
    assert created["status"] == PartnerOnboardingStatus.REQUESTED.value

    invalid_token_response = client.get(
        f"/api/v1/partner-onboarding/portal/{onboarding_id}/progress",
        headers={"X-Onboarding-Token": "not-the-token"},
    )
    assert invalid_token_response.status_code == 404

    premature_submit = client.post(
        f"/api/v1/partner-onboarding/portal/{onboarding_id}/submit",
        headers={"X-Onboarding-Token": portal_token},
    )
    assert premature_submit.status_code == 409

    administrator_response = client.post(
        f"/api/v1/partner-onboarding/portal/{onboarding_id}/administrators",
        headers={"X-Onboarding-Token": portal_token},
        json={
            "first_name": "Bank",
            "last_name": "Administrator",
            "email": f"bank-admin-{uuid4().hex[:10]}@example.com",
            "department": "Technology",
        },
    )
    assert administrator_response.status_code == 201, administrator_response.text
    raw_invitation_token = administrator_response.json()["data"]["invitation_token"]

    registration = _upload_required_document(
        client,
        onboarding_id=onboarding_id,
        token=portal_token,
        document_type="business_registration",
    )
    license_doc = _upload_required_document(
        client,
        onboarding_id=onboarding_id,
        token=portal_token,
        document_type="regulatory_license",
    )

    submit_response = client.post(
        f"/api/v1/partner-onboarding/portal/{onboarding_id}/submit",
        headers={"X-Onboarding-Token": portal_token},
    )
    assert submit_response.status_code == 200, submit_response.text
    assert (
        submit_response.json()["data"]["status"]
        == PartnerOnboardingStatus.BUSINESS_INFORMATION.value
    )

    platform_admin = create_test_user(
        UserRole.ADMINISTRATOR,
        f"portal-reviewer-{uuid4().hex[:10]}@example.com",
        is_platform_admin=True,
    )
    authenticate_client(client, platform_admin)

    assignment_response = client.patch(
        f"/api/v1/partner-onboarding/{onboarding_id}/assignment",
        json={"assigned_to": str(platform_admin.id)},
    )
    assert assignment_response.status_code == 200, assignment_response.text

    advance_response = client.post(
        f"/api/v1/partner-onboarding/{onboarding_id}/advance",
        json={"notes": "Required information submitted."},
    )
    assert advance_response.status_code == 200, advance_response.text
    assert (
        advance_response.json()["data"]["status"]
        == PartnerOnboardingStatus.COMPLIANCE_REVIEW.value
    )

    premature_advance = client.post(
        f"/api/v1/partner-onboarding/{onboarding_id}/advance",
        json={},
    )
    assert premature_advance.status_code == 409

    for document in (registration, license_doc):
        review_response = client.patch(
            f"/api/v1/partner-onboarding/{onboarding_id}/documents/"
            f"{document['id']}/review",
            json={
                "review_status": "APPROVED",
                "notes": "Evidence reviewed for onboarding test.",
            },
        )
        assert review_response.status_code == 200, review_response.text

    advance_response = client.post(
        f"/api/v1/partner-onboarding/{onboarding_id}/advance",
        json={"notes": "Compliance evidence approved."},
    )
    assert advance_response.status_code == 200, advance_response.text
    assert (
        advance_response.json()["data"]["status"]
        == PartnerOnboardingStatus.TECHNICAL_SETUP.value
    )

    missing_technical_setup = client.post(
        f"/api/v1/partner-onboarding/{onboarding_id}/advance",
        json={},
    )
    assert missing_technical_setup.status_code == 409

    setup_response = client.put(
        f"/api/v1/partner-onboarding/portal/{onboarding_id}/technical-setup",
        headers={"X-Onboarding-Token": portal_token},
        json={
            "target_environment": "sandbox",
            "callback_url": "https://bank.example.com/finpilot/callback",
            "allowed_ip_ranges": ["192.0.2.10/32"],
            "integration_contact_email": "integration@bank.example.com",
        },
    )
    assert setup_response.status_code == 200, setup_response.text

    advance_response = client.post(
        f"/api/v1/partner-onboarding/{onboarding_id}/advance",
        json={"notes": "Technical setup completed."},
    )
    assert advance_response.status_code == 200, advance_response.text
    assert (
        advance_response.json()["data"]["status"]
        == PartnerOnboardingStatus.API_CREDENTIALS.value
    )

    activation_response = client.post(
        f"/api/v1/partner-onboarding/{onboarding_id}/approve",
        json={"notes": "Onboarding approved in integration test."},
    )
    assert activation_response.status_code == 200, activation_response.text
    activated = activation_response.json()["data"]
    assert activated["status"] == PartnerOnboardingStatus.ACTIVE.value
    assert activated["activated_tenant_id"]
    assert activated["api_key"].startswith("fp_live_")

    db_session.expire_all()
    assert (
        db_session.query(Organization)
        .filter(Organization.tenant_id == activated["activated_tenant_id"])
        .first()
        is not None
    )
    invitation_hash = hashlib.sha256(raw_invitation_token.encode("utf-8")).hexdigest()
    assert (
        db_session.query(UserInvitation)
        .filter(UserInvitation.token_hash == invitation_hash)
        .first()
        is not None
    )
    key_hash = hashlib.sha256(activated["api_key"].encode("utf-8")).hexdigest()
    assert (
        db_session.query(APIKey).filter(APIKey.key_hash == key_hash).first() is not None
    )

    progress_response = client.get(
        f"/api/v1/partner-onboarding/{onboarding_id}/progress"
    )
    assert progress_response.status_code == 200, progress_response.text
    progress = progress_response.json()["data"]
    assert progress["status"] == PartnerOnboardingStatus.ACTIVE.value
    assert progress["progress_percent"] == 100
