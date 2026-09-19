from uuid import UUID

from app.models.compliance_case import ComplianceCase
from app.utils.enums import UserRole
from tests.helpers import (
    authenticate_client,
    create_customer_with_data,
)


def test_compliance_case_can_be_created(
    client,
    create_test_user,
    cleanup_compliance_cases,
    cleanup_test_customers,
):
    admin = create_test_user(
        email="compliance-case-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(
        client,
        admin,
    )

    customer_response = create_customer_with_data(
        client,
        email="compliance-case-customer@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    response = client.post(
        "/api/v1/compliance-cases",
        json={
            "customer_id": customer_id,
            "case_type": "CUSTOMER_REVIEW",
            "priority": "HIGH",
            "description": "Customer requires compliance review.",
        },
    )

    assert response.status_code == 201

    data = response.json()["data"]

    assert data["customer_id"] == customer_id
    assert data["case_type"] == "CUSTOMER_REVIEW"
    assert data["priority"] == "HIGH"
    assert data["status"] == "OPEN"
    assert data["description"] == ("Customer requires compliance review.")
    assert data["assigned_to"] is None
    assert data["closed_at"] is None
    assert data["created_at"] is not None
    assert data["updated_at"] is not None


def test_compliance_case_is_linked_to_customer(
    client,
    create_test_user,
    cleanup_compliance_cases,
    cleanup_test_customers,
):
    admin = create_test_user(
        email="compliance-link-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(
        client,
        admin,
    )

    customer_response = create_customer_with_data(
        client,
        email="compliance-link-customer@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    create_response = client.post(
        "/api/v1/compliance-cases",
        json={
            "customer_id": customer_id,
            "case_type": "AML_ALERT",
            "priority": "CRITICAL",
            "description": "AML alert requires review.",
        },
    )

    assert create_response.status_code == 201

    case_id = create_response.json()["data"]["id"]

    response = client.get(
        f"/api/v1/compliance-cases/customer/{customer_id}",
    )

    assert response.status_code == 200

    cases = response.json()["data"]

    assert len(cases) == 1
    assert cases[0]["id"] == case_id
    assert cases[0]["customer_id"] == customer_id


def test_compliance_case_can_be_retrieved(
    client,
    create_test_user,
    cleanup_compliance_cases,
    cleanup_test_customers,
):
    admin = create_test_user(
        email="compliance-get-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(
        client,
        admin,
    )

    customer_response = create_customer_with_data(
        client,
        email="compliance-get-customer@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    create_response = client.post(
        "/api/v1/compliance-cases",
        json={
            "customer_id": customer_id,
            "case_type": "VERIFICATION_ISSUE",
            "priority": "MEDIUM",
            "description": "Verification issue requires investigation.",
        },
    )

    assert create_response.status_code == 201

    case_id = create_response.json()["data"]["id"]

    response = client.get(
        f"/api/v1/compliance-cases/{case_id}",
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["id"] == case_id
    assert data["customer_id"] == customer_id
    assert data["case_type"] == "VERIFICATION_ISSUE"
    assert data["priority"] == "MEDIUM"
    assert data["status"] == "OPEN"


def test_compliance_case_status_is_stored(
    client,
    create_test_user,
    cleanup_compliance_cases,
    cleanup_test_customers,
    db_session,
):
    admin = create_test_user(
        email="compliance-status-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(
        client,
        admin,
    )

    customer_response = create_customer_with_data(
        client,
        email="compliance-status-customer@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    response = client.post(
        "/api/v1/compliance-cases",
        json={
            "customer_id": customer_id,
            "case_type": "MANUAL_INVESTIGATION",
            "priority": "LOW",
        },
    )

    assert response.status_code == 201

    case_id = response.json()["data"]["id"]

    case = (
        db_session.query(ComplianceCase)
        .filter(ComplianceCase.id == UUID(case_id))
        .first()
    )

    assert case is not None
    assert case.status.value == "OPEN"


def test_compliance_cases_can_be_filtered_by_status(
    client,
    create_test_user,
    cleanup_compliance_cases,
    cleanup_test_customers,
):
    admin = create_test_user(
        email="compliance-filter-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(
        client,
        admin,
    )

    customer_response = create_customer_with_data(
        client,
        email="compliance-filter-customer@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    create_response = client.post(
        "/api/v1/compliance-cases",
        json={
            "customer_id": customer_id,
            "case_type": "CUSTOMER_REVIEW",
            "priority": "HIGH",
        },
    )

    assert create_response.status_code == 201

    response = client.get(
        "/api/v1/compliance-cases",
        params={
            "status": "OPEN",
        },
    )

    assert response.status_code == 200

    cases = response.json()["data"]

    assert all(case["status"] == "OPEN" for case in cases)


def test_compliance_cases_can_be_filtered_by_type(
    client,
    create_test_user,
    cleanup_compliance_cases,
    cleanup_test_customers,
):
    admin = create_test_user(
        email="compliance-type-filter-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(
        client,
        admin,
    )

    customer_response = create_customer_with_data(
        client,
        email="compliance-type-filter-customer@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    response = client.post(
        "/api/v1/compliance-cases",
        json={
            "customer_id": customer_id,
            "case_type": "AML_ALERT",
            "priority": "HIGH",
        },
    )

    assert response.status_code == 201

    response = client.get(
        "/api/v1/compliance-cases",
        params={
            "case_type": "AML_ALERT",
        },
    )

    assert response.status_code == 200

    cases = response.json()["data"]

    assert all(case["case_type"] == "AML_ALERT" for case in cases)


def test_compliance_officer_can_create_case(
    client,
    create_test_user,
    cleanup_compliance_cases,
    cleanup_test_customers,
):
    admin = create_test_user(
        email="case-reader-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    compliance_officer = create_test_user(
        email="compliance-officer-case@example.com",
        role=UserRole.COMPLIANCE_OFFICER,
    )

    authenticate_client(
        client,
        admin,
    )

    customer_response = create_customer_with_data(
        client,
        email="compliance-officer-customer@example.com",
    )

    assert customer_response.status_code == 201

    authenticate_client(
        client,
        compliance_officer,
    )

    customer_id = customer_response.json()["data"]["id"]

    response = client.post(
        "/api/v1/compliance-cases",
        json={
            "customer_id": customer_id,
            "case_type": "CUSTOMER_REVIEW",
            "priority": "HIGH",
        },
    )

    assert response.status_code == 201


def test_reviewer_can_read_compliance_cases(
    client,
    create_test_user,
    cleanup_compliance_cases,
    cleanup_test_customers,
):
    admin = create_test_user(
        email="case-reader-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(
        client,
        admin,
    )

    customer_response = create_customer_with_data(
        client,
        email="case-reader-customer@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    create_response = client.post(
        "/api/v1/compliance-cases",
        json={
            "customer_id": customer_id,
            "case_type": "CUSTOMER_REVIEW",
            "priority": "MEDIUM",
        },
    )

    assert create_response.status_code == 201

    reviewer = create_test_user(
        email="case-reader-reviewer@example.com",
        role=UserRole.REVIEWER,
    )

    authenticate_client(
        client,
        reviewer,
    )

    response = client.get(
        "/api/v1/compliance-cases",
    )

    assert response.status_code == 200


def test_auditor_cannot_create_compliance_case(
    client,
    create_test_user,
    cleanup_compliance_cases,
    cleanup_test_customers,
):
    admin = create_test_user(
        email="case@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    auditor = create_test_user(
        email="case-auditor@example.com",
        role=UserRole.AUDITOR,
    )

    authenticate_client(
        client,
        admin,
    )

    customer_response = create_customer_with_data(
        client,
        email="case-auditor-customer@example.com",
    )

    assert customer_response.status_code == 201

    authenticate_client(
        client,
        auditor,
    )

    customer_id = customer_response.json()["data"]["id"]

    response = client.post(
        "/api/v1/compliance-cases",
        json={
            "customer_id": customer_id,
            "case_type": "AML_ALERT",
            "priority": "HIGH",
        },
    )

    assert response.status_code == 403


def test_compliance_case_requires_existing_customer(
    client,
    create_test_user,
    cleanup_compliance_cases,
):
    admin = create_test_user(
        email="case-missing-customer@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(
        client,
        admin,
    )

    response = client.post(
        "/api/v1/compliance-cases",
        json={
            "customer_id": "00000000-0000-0000-0000-000000000000",
            "case_type": "CUSTOMER_REVIEW",
            "priority": "HIGH",
        },
    )

    assert response.status_code == 404


def test_compliance_case_requires_existing_assigned_user(
    client,
    create_test_user,
    cleanup_compliance_cases,
    cleanup_test_customers,
):
    admin = create_test_user(
        email="case-missing-assignee@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(
        client,
        admin,
    )

    customer_response = create_customer_with_data(
        client,
        email="case-missing-assignee-customer@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    response = client.post(
        "/api/v1/compliance-cases",
        json={
            "customer_id": customer_id,
            "case_type": "CUSTOMER_REVIEW",
            "priority": "HIGH",
            "assigned_to": "00000000-0000-0000-0000-000000000000",
        },
    )

    assert response.status_code == 404
