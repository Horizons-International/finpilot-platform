import uuid
from datetime import datetime, timezone

from app.models.document import CustomerDocument
from app.models.verification_case import IdentityVerificationCase
from app.providers.schemas import (
    VerificationRequest,
    VerificationResponse,
)
from app.providers.verification_provider import VerificationProvider
from app.utils.enums import (
    DocumentStatus,
    UserRole,
    VerificationStatus,
)


def authenticate_client(client, user):
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": user.email,
            "password": "Password123!",
        },
    )

    assert response.status_code == 200

    token = response.json()["data"]["access_token"]

    client.headers.update(
        {
            "Authorization": f"Bearer {token}",
        }
    )


def create_customer_with_data(client, **overrides):
    data = {
        "first_name": "John",
        "middle_name": "Michael",
        "last_name": "Smith",
        "date_of_birth": "1990-05-15",
        "nationality": "US",
        "country_of_residence": "US",
        "email": "john.smith@example.com",
        "phone_number": "+249912345678",
        "status": "new",
    }

    data.update(overrides)

    return client.post(
        "/api/v1/customers",
        json=data,
    )


def create_verification_case(client, customer_id):
    response = client.post(
        f"/api/v1/customers/{customer_id}/verification",
        json={
            "verification_type": "IDENTITY",
        },
    )

    assert response.status_code == 201

    return response.json()["data"]


class FakeVerificationProvider(VerificationProvider):
    def __init__(self):
        self.request = None

    def verify(
        self,
        request: VerificationRequest,
    ) -> VerificationResponse:
        self.request = request

        return VerificationResponse(
            provider_name="fake",
            verification_case_id=request.verification_case_id,
            status=VerificationStatus.APPROVED,
            reference_id="fake-reference-123",
            message="Verification approved.",
        )


def create_report_customer(client, suffix):
    response = create_customer_with_data(
        client,
        first_name="Report",
        last_name=f"Customer{suffix}",
        email=f"report-customer-{suffix}@example.com",
    )

    assert response.status_code == 201

    return response.json()["data"]["id"]


def create_report_verification_case(
    client,
    customer_id,
    verification_type="IDENTITY",
):
    response = client.post(
        f"/api/v1/customers/{customer_id}/verification",
        json={
            "verification_type": verification_type,
        },
    )

    assert response.status_code == 201

    return response.json()["data"]["id"]


def set_verification_case_status(
    db_session,
    case_id,
    status,
    created_at=None,
):
    case = (
        db_session.query(IdentityVerificationCase)
        .filter(IdentityVerificationCase.id == uuid.UUID(str(case_id)))
        .first()
    )

    assert case is not None

    case.status = status

    if created_at is not None:
        case.created_at = created_at

    db_session.commit()
    db_session.refresh(case)

    return case


# ---------------------------------------------------------------------------
# Verification reporting
# ---------------------------------------------------------------------------


def test_verification_summary_returns_accurate_counts(
    client,
    db_session,
    create_test_user,
    cleanup_test_files,
    cleanup_test_customers,
):
    _, admin = create_test_user(
        email="verification-report-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    customer_id1 = create_report_customer(client, "counts")
    customer_id2 = create_report_customer(client, "count")
    customer_id3 = create_report_customer(client, "coun")

    pending_case_id = create_report_verification_case(
        client,
        customer_id1,
    )

    approved_case_id = create_report_verification_case(
        client,
        customer_id2,
    )

    rejected_case_id = create_report_verification_case(
        client,
        customer_id3,
    )

    set_verification_case_status(
        db_session,
        approved_case_id,
        VerificationStatus.APPROVED,
    )

    set_verification_case_status(
        db_session,
        rejected_case_id,
        VerificationStatus.REJECTED,
    )

    response = client.get(
        "/api/v1/reports/verification-summary",
    )

    assert response.status_code == 200

    data = response.json()["data"]

    cleanup_test_files(rejected_case_id)
    cleanup_test_files(approved_case_id)
    cleanup_test_files(pending_case_id)

    assert data["total_cases"] == 3
    assert data["pending_cases"] == 1
    assert data["approved_cases"] == 1
    assert data["rejected_cases"] == 1


def test_verification_summary_status_filter(
    client,
    db_session,
    create_test_user,
    cleanup_test_files,
    cleanup_test_customers,
):
    _, admin = create_test_user(
        email="verification-status-report-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    customer_id1 = create_report_customer(client, "status")
    customer_id2 = create_report_customer(client, "statuss")
    customer_id3 = create_report_customer(client, "statusss")

    pending_case_id = create_report_verification_case(
        client,
        customer_id1,
    )

    approved_case_id = create_report_verification_case(
        client,
        customer_id2,
    )

    rejected_case_id = create_report_verification_case(
        client,
        customer_id3,
    )

    set_verification_case_status(
        db_session,
        approved_case_id,
        VerificationStatus.APPROVED,
    )

    set_verification_case_status(
        db_session,
        rejected_case_id,
        VerificationStatus.REJECTED,
    )

    response = client.get(
        "/api/v1/reports/verification-summary",
        params={
            "status": VerificationStatus.APPROVED.value,
        },
    )

    assert response.status_code == 200

    data = response.json()["data"]

    cleanup_test_files(rejected_case_id)
    cleanup_test_files(approved_case_id)
    cleanup_test_files(pending_case_id)

    assert data["total_cases"] == 1
    assert data["pending_cases"] == 0
    assert data["approved_cases"] == 1
    assert data["rejected_cases"] == 0


def test_verification_summary_date_filter(
    client,
    db_session,
    create_test_user,
    cleanup_test_files,
    cleanup_test_customers,
):
    _, admin = create_test_user(
        email="verification-date-report-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    customer_id1 = create_report_customer(client, "date")
    customer_id2 = create_report_customer(client, "datee")

    january_case_id = create_report_verification_case(
        client,
        customer_id1,
    )

    february_case_id = create_report_verification_case(
        client,
        customer_id2,
    )

    set_verification_case_status(
        db_session,
        january_case_id,
        VerificationStatus.APPROVED,
        datetime(2026, 1, 15, tzinfo=timezone.utc),
    )

    set_verification_case_status(
        db_session,
        february_case_id,
        VerificationStatus.APPROVED,
        datetime(2026, 2, 15, tzinfo=timezone.utc),
    )

    response = client.get(
        "/api/v1/reports/verification-summary",
        params={
            "date_from": "2026-01-01",
            "date_to": "2026-01-31",
        },
    )

    assert response.status_code == 200

    data = response.json()["data"]

    cleanup_test_files(february_case_id)
    cleanup_test_files(january_case_id)

    assert data["total_cases"] == 1
    assert data["pending_cases"] == 0
    assert data["approved_cases"] == 1
    assert data["rejected_cases"] == 0


def test_verification_summary_combined_filters(
    client,
    db_session,
    create_test_user,
    cleanup_test_files,
    cleanup_test_customers,
):
    _, admin = create_test_user(
        email="verification-combined-report-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    customer_id1 = create_report_customer(client, "combined")
    customer_id2 = create_report_customer(client, "combinedd")
    customer_id3 = create_report_customer(client, "combineddd")

    january_approved_id = create_report_verification_case(
        client,
        customer_id1,
    )

    january_rejected_id = create_report_verification_case(
        client,
        customer_id2,
    )

    february_approved_id = create_report_verification_case(
        client,
        customer_id3,
    )

    set_verification_case_status(
        db_session,
        january_approved_id,
        VerificationStatus.APPROVED,
        datetime(2026, 1, 15, tzinfo=timezone.utc),
    )

    set_verification_case_status(
        db_session,
        january_rejected_id,
        VerificationStatus.REJECTED,
        datetime(2026, 1, 20, tzinfo=timezone.utc),
    )

    set_verification_case_status(
        db_session,
        february_approved_id,
        VerificationStatus.APPROVED,
        datetime(2026, 2, 15, tzinfo=timezone.utc),
    )

    response = client.get(
        "/api/v1/reports/verification-summary",
        params={
            "date_from": "2026-01-01",
            "date_to": "2026-01-31",
            "status": VerificationStatus.APPROVED.value,
        },
    )

    assert response.status_code == 200

    data = response.json()["data"]

    cleanup_test_files(january_approved_id)
    cleanup_test_files(january_rejected_id)
    cleanup_test_files(february_approved_id)

    assert data["total_cases"] == 1
    assert data["pending_cases"] == 0
    assert data["approved_cases"] == 1
    assert data["rejected_cases"] == 0


def test_verification_summary_returns_zero_when_no_cases(
    client,
    create_test_user,
    cleanup_test_files,
    cleanup_test_customers,
):
    _, admin = create_test_user(
        email="verification-empty-report-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    response = client.get(
        "/api/v1/reports/verification-summary",
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["total_cases"] == 0
    assert data["pending_cases"] == 0
    assert data["approved_cases"] == 0
    assert data["rejected_cases"] == 0


# ---------------------------------------------------------------------------
# Document reporting
# ---------------------------------------------------------------------------


def create_report_document(
    db_session,
    customer_id,
    verification_case_id,
    uploaded_by,
    status,
    created_at=None,
):
    document = CustomerDocument(
        customer_id=uuid.UUID(str(customer_id)),
        verification_case_id=uuid.UUID(str(verification_case_id)),
        document_type_id="00000000-0000-0000-0000-000000000001",
        uploaded_by=uploaded_by,
        file_reference=f"report-file-{uuid.uuid4()}",
        file_name="report.pdf",
        file_type="application/pdf",
        file_size=1024,
        status=status,
    )

    db_session.add(document)
    db_session.flush()

    if created_at is not None:
        document.created_at = created_at

    db_session.commit()
    db_session.refresh(document)

    return document


def test_document_summary_returns_accurate_counts(
    client,
    db_session,
    create_test_user,
    cleanup_test_files,
    cleanup_test_customers,
):
    _, admin = create_test_user(
        email="document-report-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    customer_id = create_report_customer(client, "documents")

    case_id = create_report_verification_case(
        client,
        customer_id,
    )

    create_report_document(
        db_session,
        customer_id,
        case_id,
        admin.id,
        DocumentStatus.UPLOADED,
    )

    create_report_document(
        db_session,
        customer_id,
        case_id,
        admin.id,
        DocumentStatus.VERIFIED,
    )

    create_report_document(
        db_session,
        customer_id,
        case_id,
        admin.id,
        DocumentStatus.REJECTED,
    )

    response = client.get(
        "/api/v1/reports/document-summary",
    )

    assert response.status_code == 200

    data = response.json()["data"]

    cleanup_test_files(case_id)

    assert data["uploaded_documents"] == 3
    assert data["accepted_documents"] == 1
    assert data["rejected_documents"] == 1


def test_document_summary_status_filter(
    client,
    db_session,
    create_test_user,
    cleanup_test_files,
    cleanup_test_customers,
):
    _, admin = create_test_user(
        email="document-status-report-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    customer_id = create_report_customer(client, "document-status")

    case_id = create_report_verification_case(
        client,
        customer_id,
    )

    create_report_document(
        db_session,
        customer_id,
        case_id,
        admin.id,
        DocumentStatus.VERIFIED,
    )

    create_report_document(
        db_session,
        customer_id,
        case_id,
        admin.id,
        DocumentStatus.REJECTED,
    )

    response = client.get(
        "/api/v1/reports/document-summary",
        params={
            "status": DocumentStatus.VERIFIED.value,
        },
    )

    assert response.status_code == 200

    data = response.json()["data"]

    cleanup_test_files(case_id)

    assert data["uploaded_documents"] == 1
    assert data["accepted_documents"] == 1
    assert data["rejected_documents"] == 0


def test_document_summary_date_filter(
    client,
    db_session,
    create_test_user,
    cleanup_test_files,
    cleanup_test_customers,
):
    _, admin = create_test_user(
        email="document-date-report-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    customer_id = create_report_customer(client, "document-date")

    case_id = create_report_verification_case(
        client,
        customer_id,
    )

    create_report_document(
        db_session,
        customer_id,
        case_id,
        admin.id,
        DocumentStatus.VERIFIED,
        datetime(2026, 1, 15, tzinfo=timezone.utc),
    )

    create_report_document(
        db_session,
        customer_id,
        case_id,
        admin.id,
        DocumentStatus.VERIFIED,
        datetime(2026, 2, 15, tzinfo=timezone.utc),
    )

    response = client.get(
        "/api/v1/reports/document-summary",
        params={
            "date_from": "2026-01-01",
            "date_to": "2026-01-31",
        },
    )

    assert response.status_code == 200

    data = response.json()["data"]

    cleanup_test_files(case_id)

    assert data["uploaded_documents"] == 1
    assert data["accepted_documents"] == 1
    assert data["rejected_documents"] == 0


def test_document_summary_combined_filters(
    client,
    db_session,
    create_test_user,
    cleanup_test_files,
    cleanup_test_customers,
):
    _, admin = create_test_user(
        email="document-combined-report-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    customer_id = create_report_customer(client, "document-combined")

    case_id = create_report_verification_case(
        client,
        customer_id,
    )

    create_report_document(
        db_session,
        customer_id,
        case_id,
        admin.id,
        DocumentStatus.VERIFIED,
        datetime(2026, 1, 15, tzinfo=timezone.utc),
    )

    create_report_document(
        db_session,
        customer_id,
        case_id,
        admin.id,
        DocumentStatus.REJECTED,
        datetime(2026, 1, 20, tzinfo=timezone.utc),
    )

    create_report_document(
        db_session,
        customer_id,
        case_id,
        admin.id,
        DocumentStatus.VERIFIED,
        datetime(2026, 2, 15, tzinfo=timezone.utc),
    )

    response = client.get(
        "/api/v1/reports/document-summary",
        params={
            "date_from": "2026-01-01",
            "date_to": "2026-01-31",
            "status": DocumentStatus.VERIFIED.value,
        },
    )

    assert response.status_code == 200

    data = response.json()["data"]

    cleanup_test_files(case_id)

    assert data["uploaded_documents"] == 1
    assert data["accepted_documents"] == 1
    assert data["rejected_documents"] == 0


def test_document_summary_returns_zero_when_no_documents(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, admin = create_test_user(
        email="document-empty-report-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    response = client.get(
        "/api/v1/reports/document-summary",
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["uploaded_documents"] == 0
    assert data["accepted_documents"] == 0
    assert data["rejected_documents"] == 0


# ---------------------------------------------------------------------------
# Reporting authorization
# ---------------------------------------------------------------------------


def test_admin_can_access_verification_report(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, admin = create_test_user(
        email="report-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    response = client.get(
        "/api/v1/reports/verification-summary",
    )

    assert response.status_code == 200


def test_compliance_officer_can_access_verification_report(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, compliance_officer = create_test_user(
        email="report-compliance@example.com",
        role=UserRole.COMPLIANCE_OFFICER,
    )

    authenticate_client(client, compliance_officer)

    response = client.get(
        "/api/v1/reports/verification-summary",
    )

    assert response.status_code == 200


def test_auditor_can_access_verification_report(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, auditor = create_test_user(
        email="report-auditor@example.com",
        role=UserRole.AUDITOR,
    )

    authenticate_client(client, auditor)

    response = client.get(
        "/api/v1/reports/verification-summary",
    )

    assert response.status_code == 200


def test_reviewer_cannot_access_verification_report(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, reviewer = create_test_user(
        email="report-reviewer@example.com",
        role=UserRole.REVIEWER,
    )

    authenticate_client(client, reviewer)

    response = client.get(
        "/api/v1/reports/verification-summary",
    )

    assert response.status_code == 403


def test_unauthenticated_user_cannot_access_verification_report(
    client,
):
    response = client.get(
        "/api/v1/reports/verification-summary",
    )

    assert response.status_code == 401


def test_reviewer_cannot_access_document_report(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, reviewer = create_test_user(
        email="document-report-reviewer@example.com",
        role=UserRole.REVIEWER,
    )

    authenticate_client(client, reviewer)

    response = client.get(
        "/api/v1/reports/document-summary",
    )

    assert response.status_code == 403


def test_auditor_can_access_document_report(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, auditor = create_test_user(
        email="document-report-auditor@example.com",
        role=UserRole.AUDITOR,
    )

    authenticate_client(client, auditor)

    response = client.get(
        "/api/v1/reports/document-summary",
    )

    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Reporting validation
# ---------------------------------------------------------------------------


def test_verification_report_rejects_invalid_date_range(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, admin = create_test_user(
        email="invalid-date-report-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    response = client.get(
        "/api/v1/reports/verification-summary",
        params={
            "date_from": "2026-02-01",
            "date_to": "2026-01-01",
        },
    )

    assert response.status_code == 400

    assert response.json()["message"] == "date_from cannot be later than date_to."


def test_document_report_rejects_invalid_date_range(
    client,
    create_test_user,
    cleanup_test_customers,
):
    _, admin = create_test_user(
        email="invalid-document-date-report-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    response = client.get(
        "/api/v1/reports/document-summary",
        params={
            "date_from": "2026-02-01",
            "date_to": "2026-01-01",
        },
    )

    assert response.status_code == 400

    assert response.json()["message"] == "date_from cannot be later than date_to."
