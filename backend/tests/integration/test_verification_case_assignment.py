import time
import uuid

from app.models.audit_log import AuditLog
from app.models.verification_case import IdentityVerificationCase
from app.models.verification_case_assignment_history import (
    VerificationCaseAssignmentHistory,
)
from app.utils.enums import (
    AuditEventType,
    UserRole,
)
from tests.helpers import (
    authenticate_client,
    create_customer_with_data,
    create_verification_case,
)


def test_manager_can_assign_case_to_reviewer(
    client,
    db_session,
    create_test_user,
    cleanup_test_customers,
    cleanup_verification_case_assignments,
):
    manager = create_test_user(
        email=f"assignment-manager-{uuid.uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    reviewer = create_test_user(
        email=f"assignment-reviewer-{uuid.uuid4()}@example.com",
        role=UserRole.REVIEWER,
    )

    authenticate_client(client, manager)

    customer_response = create_customer_with_data(
        client,
        email=f"assignment-customer-{uuid.uuid4()}@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    case = create_verification_case(
        client,
        customer_id,
    )

    case_id = case["id"]

    response = client.patch(
        f"/api/v1/customers/{customer_id}/verification-cases/{case_id}/assignment",
        json={
            "assigned_to": str(reviewer.id),
        },
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["verification_case_id"] == case_id
    assert data["assigned_to"] == str(reviewer.id)
    assert data["assigned_by"] == str(manager.id)
    assert data["previous_reviewer"] is None
    assert data["assigned_at"] is not None

    db_session.expire_all()

    saved_case = (
        db_session.query(IdentityVerificationCase)
        .filter(
            IdentityVerificationCase.id == case_id,
        )
        .first()
    )

    assert saved_case is not None
    assert saved_case.assigned_to == reviewer.id
    assert saved_case.assigned_at is not None
    assert saved_case.assigned_by == manager.id

    history = (
        db_session.query(VerificationCaseAssignmentHistory)
        .filter(
            VerificationCaseAssignmentHistory.verification_case_id == uuid.UUID(case_id)
        )
        .all()
    )

    assert len(history) == 1
    assert history[0].assigned_to == reviewer.id
    assert history[0].previous_reviewer is None
    assert history[0].assigned_by == manager.id


def test_manager_can_reassign_case(
    client,
    db_session,
    create_test_user,
    cleanup_test_customers,
    cleanup_verification_case_assignments,
):
    admin = create_test_user(
        email=f"reassign-admin-{uuid.uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    manager = create_test_user(
        email=f"reassign-manager-{uuid.uuid4()}@example.com",
        role=UserRole.COMPLIANCE_OFFICER,
    )

    first_reviewer = create_test_user(
        email=f"first-reviewer-{uuid.uuid4()}@example.com",
        role=UserRole.REVIEWER,
    )

    second_reviewer = create_test_user(
        email=f"second-reviewer-{uuid.uuid4()}@example.com",
        role=UserRole.REVIEWER,
    )

    authenticate_client(client, admin)

    customer_response = create_customer_with_data(
        client,
        email=f"reassign-customer-{uuid.uuid4()}@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    authenticate_client(client, manager)

    case = create_verification_case(
        client,
        customer_id,
    )

    case_id = case["id"]

    first_response = client.patch(
        f"/api/v1/customers/{customer_id}/verification-cases/{case_id}/assignment",
        json={
            "assigned_to": str(first_reviewer.id),
        },
    )

    assert first_response.status_code == 200

    second_response = client.patch(
        f"/api/v1/customers/{customer_id}/verification-cases/{case_id}/assignment",
        json={
            "assigned_to": str(second_reviewer.id),
        },
    )

    assert second_response.status_code == 200

    data = second_response.json()["data"]

    assert data["assigned_to"] == str(second_reviewer.id)
    assert data["previous_reviewer"] == str(first_reviewer.id)

    db_session.expire_all()

    saved_case = (
        db_session.query(IdentityVerificationCase)
        .filter(
            IdentityVerificationCase.id == case_id,
        )
        .first()
    )

    assert saved_case is not None
    assert saved_case.assigned_to == second_reviewer.id

    history = (
        db_session.query(VerificationCaseAssignmentHistory)
        .filter(
            VerificationCaseAssignmentHistory.verification_case_id == uuid.UUID(case_id)
        )
        .order_by(VerificationCaseAssignmentHistory.assigned_at.asc())
        .all()
    )

    assert len(history) == 2

    assert history[0].assigned_to == first_reviewer.id
    assert history[0].previous_reviewer is None

    assert history[1].assigned_to == second_reviewer.id
    assert history[1].previous_reviewer == first_reviewer.id


def test_cannot_assign_case_to_same_reviewer(
    client,
    create_test_user,
    cleanup_test_customers,
    cleanup_verification_case_assignments,
):
    manager = create_test_user(
        email=f"same-assignment-manager-{uuid.uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    reviewer = create_test_user(
        email=f"same-assignment-reviewer-{uuid.uuid4()}@example.com",
        role=UserRole.REVIEWER,
    )

    authenticate_client(client, manager)

    customer_response = create_customer_with_data(
        client,
        email=f"same-assignment-customer-{uuid.uuid4()}@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    case = create_verification_case(
        client,
        customer_id,
    )

    case_id = case["id"]

    first_response = client.patch(
        f"/api/v1/customers/{customer_id}/verification-cases/{case_id}/assignment",
        json={
            "assigned_to": str(reviewer.id),
        },
    )

    assert first_response.status_code == 200

    response = client.patch(
        f"/api/v1/customers/{customer_id}/verification-cases/{case_id}/assignment",
        json={
            "assigned_to": str(reviewer.id),
        },
    )

    assert response.status_code == 400


def test_cannot_assign_case_to_non_reviewer(
    client,
    create_test_user,
    cleanup_test_customers,
    cleanup_verification_case_assignments,
):
    manager = create_test_user(
        email=f"non-reviewer-manager-{uuid.uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    auditor = create_test_user(
        email=f"non-reviewer-user-{uuid.uuid4()}@example.com",
        role=UserRole.AUDITOR,
    )

    authenticate_client(client, manager)

    customer_response = create_customer_with_data(
        client,
        email=f"non-reviewer-customer-{uuid.uuid4()}@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    case = create_verification_case(
        client,
        customer_id,
    )

    case_id = case["id"]

    response = client.patch(
        f"/api/v1/customers/{customer_id}/verification-cases/{case_id}/assignment",
        json={
            "assigned_to": str(auditor.id),
        },
    )

    assert response.status_code == 400


def test_reviewer_can_view_own_assigned_cases(
    client,
    create_test_user,
    cleanup_test_customers,
    cleanup_verification_case_assignments,
):
    manager = create_test_user(
        email=f"assigned-list-manager-{uuid.uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    reviewer = create_test_user(
        email=f"assigned-list-reviewer-{uuid.uuid4()}@example.com",
        role=UserRole.REVIEWER,
    )

    authenticate_client(client, manager)

    customer_response = create_customer_with_data(
        client,
        email=f"assigned-list-customer-{uuid.uuid4()}@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    case = create_verification_case(
        client,
        customer_id,
    )

    case_id = case["id"]

    assign_response = client.patch(
        f"/api/v1/customers/{customer_id}/verification-cases/{case_id}/assignment",
        json={
            "assigned_to": str(reviewer.id),
        },
    )

    assert assign_response.status_code == 200

    authenticate_client(client, reviewer)

    response = client.get(
        "/api/v1/verification-cases/assigned-to-me",
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["total"] == 1
    assert len(data["cases"]) == 1
    assert data["cases"][0]["verification_case_id"] == case_id
    assert data["cases"][0]["assigned_to"] == str(reviewer.id)


def test_manager_can_view_all_assigned_cases(
    client,
    create_test_user,
    cleanup_test_customers,
    cleanup_verification_case_assignments,
):
    manager = create_test_user(
        email=f"all-assigned-manager-{uuid.uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    reviewer = create_test_user(
        email=f"all-assigned-reviewer-{uuid.uuid4()}@example.com",
        role=UserRole.REVIEWER,
    )

    authenticate_client(client, manager)

    customer_response = create_customer_with_data(
        client,
        email=f"all-assigned-customer-{uuid.uuid4()}@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    case = create_verification_case(
        client,
        customer_id,
    )

    case_id = case["id"]

    assign_response = client.patch(
        f"/api/v1/customers/{customer_id}/verification-cases/{case_id}/assignment",
        json={
            "assigned_to": str(reviewer.id),
        },
    )

    assert assign_response.status_code == 200

    response = client.get(
        "/api/v1/verification-cases/assigned",
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["total"] >= 1

    matching_cases = [
        case for case in data["cases"] if case["verification_case_id"] == case_id
    ]

    assert len(matching_cases) == 1
    assert matching_cases[0]["assigned_to"] == str(reviewer.id)


def test_reviewer_cannot_assign_case(
    client,
    create_test_user,
    cleanup_test_customers,
    cleanup_verification_case_assignments,
):
    admin = create_test_user(
        email=f"assign-admin-{uuid.uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    reviewer = create_test_user(
        email=f"assign-reviewer-{uuid.uuid4()}@example.com",
        role=UserRole.REVIEWER,
    )

    target_reviewer = create_test_user(
        email=f"assign-target-{uuid.uuid4()}@example.com",
        role=UserRole.REVIEWER,
    )

    authenticate_client(client, admin)

    customer_response = create_customer_with_data(
        client,
        email=f"assign-rbac-customer-{uuid.uuid4()}@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    case = create_verification_case(
        client,
        customer_id,
    )

    case_id = case["id"]

    authenticate_client(client, reviewer)

    response = client.patch(
        f"/api/v1/customers/{customer_id}/verification-cases/{case_id}/assignment",
        json={
            "assigned_to": str(target_reviewer.id),
        },
    )

    assert response.status_code == 403


def test_auditor_cannot_assign_case(
    client,
    create_test_user,
    cleanup_test_customers,
    cleanup_verification_case_assignments,
):
    admin = create_test_user(
        email=f"assign-admin-{uuid.uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    auditor = create_test_user(
        email=f"assign-auditor-{uuid.uuid4()}@example.com",
        role=UserRole.AUDITOR,
    )

    reviewer = create_test_user(
        email=f"assign-auditor-target-{uuid.uuid4()}@example.com",
        role=UserRole.REVIEWER,
    )

    authenticate_client(client, admin)

    customer_response = create_customer_with_data(
        client,
        email=f"assign-auditor-customer-{uuid.uuid4()}@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    case = create_verification_case(
        client,
        customer_id,
    )

    case_id = case["id"]

    authenticate_client(client, auditor)

    response = client.patch(
        f"/api/v1/customers/{customer_id}/verification-cases/{case_id}/assignment",
        json={
            "assigned_to": str(reviewer.id),
        },
    )

    assert response.status_code == 403


def test_assignment_history_is_available(
    client,
    create_test_user,
    cleanup_test_customers,
    cleanup_verification_case_assignments,
):
    manager = create_test_user(
        email=f"history-manager-{uuid.uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    first_reviewer = create_test_user(
        email=f"history-first-{uuid.uuid4()}@example.com",
        role=UserRole.REVIEWER,
    )

    second_reviewer = create_test_user(
        email=f"history-second-{uuid.uuid4()}@example.com",
        role=UserRole.REVIEWER,
    )

    authenticate_client(client, manager)

    customer_response = create_customer_with_data(
        client,
        email=f"history-customer-{uuid.uuid4()}@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    case = create_verification_case(
        client,
        customer_id,
    )

    case_id = case["id"]

    response = client.patch(
        f"/api/v1/customers/{customer_id}/verification-cases/{case_id}/assignment",
        json={
            "assigned_to": str(first_reviewer.id),
        },
    )

    assert response.status_code == 200

    time.sleep(1)

    response = client.patch(
        f"/api/v1/customers/{customer_id}/verification-cases/{case_id}/assignment",
        json={
            "assigned_to": str(second_reviewer.id),
        },
    )

    assert response.status_code == 200

    response = client.get(
        f"/api/v1/customers/{customer_id}/"
        f"verification-cases/{case_id}/assignment-history",
    )

    assert response.status_code == 200

    history = response.json()["data"]

    assert len(history) == 2

    # API returns newest first.
    assert history[0]["assigned_to"] == str(second_reviewer.id)
    assert history[0]["previous_reviewer"] == str(first_reviewer.id)

    assert history[1]["assigned_to"] == str(first_reviewer.id)
    assert history[1]["previous_reviewer"] is None


def test_assignment_is_audited(
    client,
    db_session,
    create_test_user,
    cleanup_test_customers,
    cleanup_verification_case_assignments,
):
    manager = create_test_user(
        email=f"audit-assignment-manager-{uuid.uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    reviewer = create_test_user(
        email=f"audit-assignment-reviewer-{uuid.uuid4()}@example.com",
        role=UserRole.REVIEWER,
    )

    authenticate_client(client, manager)

    customer_response = create_customer_with_data(
        client,
        email=f"audit-assignment-customer-{uuid.uuid4()}@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    case = create_verification_case(
        client,
        customer_id,
    )

    case_id = case["id"]

    response = client.patch(
        f"/api/v1/customers/{customer_id}/verification-cases/{case_id}/assignment",
        json={
            "assigned_to": str(reviewer.id),
        },
    )

    assert response.status_code == 200

    db_session.expire_all()

    audit_log = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.user_id == manager.id,
            AuditLog.event_type == AuditEventType.VERIFICATION_CASE_ASSIGNED,
            AuditLog.resource_type == "verification_case",
            AuditLog.resource_id == case_id,
        )
        .order_by(AuditLog.timestamp.desc())
        .first()
    )

    assert audit_log is not None


def test_assign_nonexistent_case_returns_404(
    client,
    create_test_user,
):
    manager = create_test_user(
        email=f"missing-assignment-manager-{uuid.uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    reviewer = create_test_user(
        email=f"missing-assignment-reviewer-{uuid.uuid4()}@example.com",
        role=UserRole.REVIEWER,
    )

    authenticate_client(client, manager)

    response = client.patch(
        "/api/v1/customers/"
        "00000000-0000-0000-0000-000000000000/"
        "verification-cases/"
        "00000000-0000-0000-0000-000000000000/"
        "assignment",
        json={
            "assigned_to": str(reviewer.id),
        },
    )

    assert response.status_code == 404


def test_reassigned_reviewer_loses_review_access(
    client,
    db_session,
    create_test_user,
    cleanup_test_customers,
    cleanup_verification_case_assignments,
):
    manager = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email=f"reassign-review-manager-{uuid.uuid4()}@example.com",
    )

    first_reviewer = create_test_user(
        role=UserRole.REVIEWER,
        email=f"reassign-first-{uuid.uuid4()}@example.com",
    )

    second_reviewer = create_test_user(
        role=UserRole.REVIEWER,
        email=f"reassign-second-{uuid.uuid4()}@example.com",
    )

    authenticate_client(client, manager)

    customer_response = create_customer_with_data(
        client,
        email=f"reassign-review-customer-{uuid.uuid4()}@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    case = create_verification_case(
        client,
        customer_id,
    )

    case_id = case["id"]

    assign_first = client.patch(
        f"/api/v1/customers/{customer_id}/verification-cases/{case_id}/assignment",
        json={
            "assigned_to": str(first_reviewer.id),
        },
    )

    assert assign_first.status_code == 200

    assign_second = client.patch(
        f"/api/v1/customers/{customer_id}/verification-cases/{case_id}/assignment",
        json={
            "assigned_to": str(second_reviewer.id),
        },
    )

    assert assign_second.status_code == 200

    authenticate_client(client, first_reviewer)

    old_reviewer_response = client.post(
        f"/api/v1/customers/{customer_id}/verification-cases/{case_id}/reviews",
        json={
            "decision": "APPROVE",
            "notes": "Should no longer be allowed.",
        },
    )

    assert old_reviewer_response.status_code in {
        404,
        403,
    }
