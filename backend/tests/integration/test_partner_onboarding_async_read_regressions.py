"""Security and relationship-loading regressions for async onboarding reads."""

from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.models.audit_log import AuditLog
from app.models.partner_onboarding import (
    PartnerOnboarding,
    PartnerOnboardingAdministrator,
    PartnerOnboardingDocument,
    PartnerOnboardingHistory,
)
from app.utils.date_time import utc_now
from app.utils.enums import UserRole
from tests.helpers import authenticate_client


def _portal_payload() -> dict[str, object]:
    return {
        "organization_name": f"Read Regression Bank {uuid4().hex[:8]}",
        "legal_name": "Read Regression Bank Limited",
        "registration_number": f"REG-{uuid4().hex[:10].upper()}",
        "tax_identification_number": f"TAX-{uuid4().hex[:10].upper()}",
        "industry": "Financial Services",
        "business_description": "Partner onboarding asynchronous read regression.",
        "contact_name": "Partner Contact",
        "contact_email": f"read-regression-{uuid4()}@example.com",
        "contact_phone": "+249912345678",
        "website": "https://partner.example",
        "country": "SD",
    }


def _create_portal(client: TestClient) -> dict[str, object]:
    response = client.post(
        "/api/v1/partner-onboarding/portal",
        json=_portal_payload(),
    )
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert isinstance(data, dict)
    return data


@pytest.fixture
def cleanup_async_onboarding_regressions(db_session):
    existing_ids = {
        onboarding_id
        for (onboarding_id,) in db_session.query(PartnerOnboarding.id).all()
    }
    yield

    db_session.expire_all()
    created_ids = {
        onboarding_id
        for (onboarding_id,) in db_session.query(PartnerOnboarding.id).all()
        if onboarding_id not in existing_ids
    }
    if created_ids:
        db_session.query(AuditLog).filter(
            AuditLog.resource_type == "partner_onboarding",
            AuditLog.resource_id.in_(created_ids),
        ).delete(synchronize_session=False)
        db_session.query(PartnerOnboardingHistory).filter(
            PartnerOnboardingHistory.onboarding_id.in_(created_ids)
        ).delete(synchronize_session=False)
        db_session.query(PartnerOnboardingDocument).filter(
            PartnerOnboardingDocument.onboarding_id.in_(created_ids)
        ).delete(synchronize_session=False)
        db_session.query(PartnerOnboardingAdministrator).filter(
            PartnerOnboardingAdministrator.onboarding_id.in_(created_ids)
        ).delete(synchronize_session=False)
        db_session.query(PartnerOnboarding).filter(
            PartnerOnboarding.id.in_(created_ids)
        ).delete(synchronize_session=False)
        db_session.commit()


def test_async_progress_reads_eagerly_load_documents_and_administrators(
    client: TestClient,
    db_session,
    create_test_user,
    cleanup_async_onboarding_regressions,
):
    """Progress must serialize non-empty relationships without async lazy loads."""
    portal = _create_portal(client)
    onboarding_id = UUID(str(portal["id"]))
    portal_token = str(portal["portal_token"])

    document = PartnerOnboardingDocument(
        onboarding_id=onboarding_id,
        document_type="business_registration",
        original_filename="registration.pdf",
        storage_path="partner-onboarding/test/registration.pdf",
        content_type="application/pdf",
        file_size=128,
        sha256="a" * 64,
    )
    administrator = PartnerOnboardingAdministrator(
        onboarding_id=onboarding_id,
        first_name="Test",
        last_name="Administrator",
        email=f"portal-admin-{uuid4()}@example.com",
        role="ORGANIZATION_ADMINISTRATOR",
        invitation_token_hash=uuid4().hex + uuid4().hex,
        status="PENDING",
    )
    db_session.add_all([document, administrator])
    db_session.commit()

    portal_response = client.get(
        f"/api/v1/partner-onboarding/portal/{onboarding_id}/progress",
        headers={"X-Onboarding-Token": portal_token},
    )
    assert portal_response.status_code == 200, portal_response.text
    portal_data = portal_response.json()["data"]
    assert len(portal_data["documents"]) == 1
    assert portal_data["documents"][0]["document_type"] == "business_registration"
    assert len(portal_data["administrators"]) == 1
    assert portal_data["administrators"][0]["email"] == administrator.email

    platform_admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email=f"onboarding-read-admin-{uuid4()}@example.com",
        is_platform_admin=True,
    )
    authenticate_client(client, platform_admin)
    internal_response = client.get(
        f"/api/v1/partner-onboarding/{onboarding_id}/progress"
    )
    assert internal_response.status_code == 200, internal_response.text
    internal_data = internal_response.json()["data"]
    assert len(internal_data["documents"]) == 1
    assert len(internal_data["administrators"]) == 1


def test_async_internal_read_endpoints_remain_platform_admin_only(
    client: TestClient,
    create_test_user,
    cleanup_async_onboarding_regressions,
):
    portal = _create_portal(client)
    onboarding_id = str(portal["id"])
    tenant_admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email=f"onboarding-non-platform-{uuid4()}@example.com",
        is_platform_admin=False,
    )
    authenticate_client(client, tenant_admin)

    paths = (
        "/api/v1/partner-onboarding",
        f"/api/v1/partner-onboarding/{onboarding_id}",
        f"/api/v1/partner-onboarding/{onboarding_id}/progress",
        f"/api/v1/partner-onboarding/{onboarding_id}/history",
        f"/api/v1/partner-onboarding/{onboarding_id}/documents",
    )
    for path in paths:
        response = client.get(path)
        assert response.status_code == 403, f"{path}: {response.text}"


def test_async_portal_progress_rejects_expired_and_invalid_tokens(
    client: TestClient,
    db_session,
    cleanup_async_onboarding_regressions,
):
    portal = _create_portal(client)
    onboarding_id = UUID(str(portal["id"]))
    portal_token = str(portal["portal_token"])

    invalid_response = client.get(
        f"/api/v1/partner-onboarding/portal/{onboarding_id}/progress",
        headers={"X-Onboarding-Token": "not-the-portal-token"},
    )
    assert invalid_response.status_code == 404

    onboarding = (
        db_session.query(PartnerOnboarding)
        .filter(PartnerOnboarding.id == onboarding_id)
        .first()
    )
    assert onboarding is not None
    onboarding.portal_token_expires_at = utc_now() - timedelta(minutes=1)
    db_session.commit()

    expired_response = client.get(
        f"/api/v1/partner-onboarding/portal/{onboarding_id}/progress",
        headers={"X-Onboarding-Token": portal_token},
    )
    assert expired_response.status_code == 401, expired_response.text
