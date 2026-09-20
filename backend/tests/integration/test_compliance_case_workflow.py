from uuid import uuid4

import pytest

from app.models.audit_log import AuditLog
from app.utils.enums import (
    AuditEventType,
    UserRole,
)
from tests.helpers import (
    authenticate_client,
    create_customer_with_data,
)


def create_compliance_case(
    client,
    *,
    email: str,
    case_type: str = "CUSTOMER_REVIEW",
    priority: str = "MEDIUM",
):
    customer_response = create_customer_with_data(
        client,
        email=email,
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    response = client.post(
        "/api/v1/compliance-cases",
        json={
            "customer_id": customer_id,
            "case_type": case_type,
            "priority": priority,
            "description": "Compliance workflow test case.",
        },
    )

    assert response.status_code == 201

    return response.json()["data"]


def assign_case(
    client,
    case_id,
    user_id,
):
    return client.patch(
        f"/api/v1/compliance-cases/{case_id}/assignment",
        json={
            "assigned_to": str(user_id),
        },
    )


def update_case_status(
    client,
    case_id,
    status,
    resolution_reason=None,
):
    payload = {
        "status": status,
    }

    if resolution_reason is not None:
        payload["resolution_reason"] = resolution_reason

    return client.patch(
        f"/api/v1/compliance-cases/{case_id}/status",
        json=payload,
    )


def test_open_can_be_assigned(
    client,
    create_test_user,
    cleanup_compliance_cases,
    cleanup_test_customers,
):
    admin = create_test_user(
        email="workflow-assign-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    reviewer = create_test_user(
        email="workflow-assign-reviewer@example.com",
        role=UserRole.REVIEWER,
    )

    authenticate_client(client, admin)

    case = create_compliance_case(
        client,
        email="workflow-assign-customer@example.com",
    )

    response = assign_case(
        client,
        case["id"],
        reviewer.id,
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["status"] == "ASSIGNED"
    assert data["assigned_to"] == str(reviewer.id)


def test_assigned_can_move_to_under_review(
    client, create_test_user, cleanup_compliance_cases, cleanup_test_customers
):
    admin = create_test_user(
        email="workflow-review-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    reviewer = create_test_user(
        email="workflow-reviewer@example.com",
        role=UserRole.REVIEWER,
    )

    authenticate_client(client, admin)

    case = create_compliance_case(
        client,
        email="workflow-review-customer@example.com",
    )

    assignment_response = assign_case(
        client,
        case["id"],
        reviewer.id,
    )

    assert assignment_response.status_code == 200

    response = update_case_status(
        client,
        case["id"],
        "UNDER_REVIEW",
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "UNDER_REVIEW"


def test_under_review_can_be_escalated(
    client, create_test_user, cleanup_compliance_cases, cleanup_test_customers
):
    admin = create_test_user(
        email="workflow-escalate-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    reviewer = create_test_user(
        email="workflow-escalate-reviewer@example.com",
        role=UserRole.REVIEWER,
    )

    authenticate_client(client, admin)

    case = create_compliance_case(
        client,
        email="workflow-escalate-customer@example.com",
    )

    assert (
        assign_case(
            client,
            case["id"],
            reviewer.id,
        ).status_code
        == 200
    )

    assert (
        update_case_status(
            client,
            case["id"],
            "UNDER_REVIEW",
        ).status_code
        == 200
    )

    response = update_case_status(
        client,
        case["id"],
        "ESCALATED",
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "ESCALATED"


def test_escalated_can_return_to_under_review(
    client, create_test_user, cleanup_compliance_cases, cleanup_test_customers
):
    admin = create_test_user(
        email="workflow-return-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    reviewer = create_test_user(
        email="workflow-return-reviewer@example.com",
        role=UserRole.REVIEWER,
    )

    authenticate_client(client, admin)

    case = create_compliance_case(
        client,
        email="workflow-return-customer@example.com",
    )

    assert (
        assign_case(
            client,
            case["id"],
            reviewer.id,
        ).status_code
        == 200
    )

    assert (
        update_case_status(
            client,
            case["id"],
            "UNDER_REVIEW",
        ).status_code
        == 200
    )

    assert (
        update_case_status(
            client,
            case["id"],
            "ESCALATED",
        ).status_code
        == 200
    )

    response = update_case_status(
        client,
        case["id"],
        "UNDER_REVIEW",
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "UNDER_REVIEW"


def test_under_review_can_be_resolved(
    client, create_test_user, cleanup_compliance_cases, cleanup_test_customers
):
    admin = create_test_user(
        email="workflow-resolve-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    reviewer = create_test_user(
        email="workflow-resolve-reviewer@example.com",
        role=UserRole.REVIEWER,
    )

    authenticate_client(client, admin)

    case = create_compliance_case(
        client,
        email="workflow-resolve-customer@example.com",
    )

    assert (
        assign_case(
            client,
            case["id"],
            reviewer.id,
        ).status_code
        == 200
    )

    assert (
        update_case_status(
            client,
            case["id"],
            "UNDER_REVIEW",
        ).status_code
        == 200
    )

    response = update_case_status(
        client,
        case["id"],
        "RESOLVED",
        resolution_reason="Compliance review completed successfully.",
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["status"] == "RESOLVED"
    assert data["resolution_reason"] == "Compliance review completed successfully."
    assert data["closed_at"] is None


def test_resolved_can_be_closed(
    client, create_test_user, cleanup_compliance_cases, cleanup_test_customers
):
    admin = create_test_user(
        email="workflow-close-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    reviewer = create_test_user(
        email="workflow-close-reviewer@example.com",
        role=UserRole.REVIEWER,
    )

    authenticate_client(client, admin)

    case = create_compliance_case(
        client,
        email="workflow-close-customer@example.com",
    )

    assert (
        assign_case(
            client,
            case["id"],
            reviewer.id,
        ).status_code
        == 200
    )

    assert (
        update_case_status(
            client,
            case["id"],
            "UNDER_REVIEW",
        ).status_code
        == 200
    )

    assert (
        update_case_status(
            client,
            case["id"],
            "RESOLVED",
            resolution_reason="Review completed.",
        ).status_code
        == 200
    )

    response = update_case_status(
        client,
        case["id"],
        "CLOSED",
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["status"] == "CLOSED"
    assert data["closed_at"] is not None


@pytest.mark.parametrize(
    ("current_status", "invalid_status"),
    [
        ("OPEN", "UNDER_REVIEW"),
        ("OPEN", "RESOLVED"),
        ("OPEN", "CLOSED"),
        ("ASSIGNED", "RESOLVED"),
        ("ASSIGNED", "CLOSED"),
        ("UNDER_REVIEW", "CLOSED"),
        ("RESOLVED", "UNDER_REVIEW"),
        ("RESOLVED", "OPEN"),
        ("CLOSED", "OPEN"),
        ("CLOSED", "ASSIGNED"),
        ("CLOSED", "UNDER_REVIEW"),
    ],
)
def test_invalid_compliance_case_transition_is_rejected(
    client,
    create_test_user,
    cleanup_compliance_cases,
    cleanup_test_customers,
    current_status,
    invalid_status,
):
    admin = create_test_user(
        email=(
            f"workflow-invalid-{current_status.lower()}-"
            f"{invalid_status.lower()}@example.com"
        ),
        role=UserRole.ADMINISTRATOR,
    )

    reviewer = create_test_user(
        email=(
            f"workflow-invalid-reviewer-"
            f"{current_status.lower()}-"
            f"{invalid_status.lower()}@example.com"
        ),
        role=UserRole.REVIEWER,
    )

    authenticate_client(client, admin)

    case = create_compliance_case(
        client,
        email=(
            f"workflow-invalid-customer-"
            f"{current_status.lower()}-"
            f"{invalid_status.lower()}@example.com"
        ),
    )

    case_id = case["id"]

    if current_status != "OPEN":
        assert (
            assign_case(
                client,
                case_id,
                reviewer.id,
            ).status_code
            == 200
        )

    if current_status in {
        "UNDER_REVIEW",
        "ESCALATED",
        "RESOLVED",
    }:
        assert (
            update_case_status(
                client,
                case_id,
                "UNDER_REVIEW",
            ).status_code
            == 200
        )

    if current_status in {
        "ESCALATED",
        "RESOLVED",
    }:
        assert (
            update_case_status(
                client,
                case_id,
                "ESCALATED",
            ).status_code
            == 200
        )

    if current_status == "RESOLVED":
        assert (
            update_case_status(
                client,
                case_id,
                "UNDER_REVIEW",
            ).status_code
            == 200
        )

        assert (
            update_case_status(
                client,
                case_id,
                "RESOLVED",
                resolution_reason="Test resolution.",
            ).status_code
            == 200
        )

    if current_status == "CLOSED":
        assert update_case_status(client, case_id, "UNDER_REVIEW")
        assert update_case_status(client, case_id, "RESOLVED")
        assert update_case_status(client, case_id, "CLOSED")

    response = update_case_status(
        client,
        case_id,
        invalid_status,
    )

    assert response.status_code == 400


def test_open_cannot_transition_directly_to_resolved(
    client, create_test_user, cleanup_compliance_cases, cleanup_test_customers
):
    admin = create_test_user(
        email="workflow-invalid-open-resolved-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    case = create_compliance_case(
        client,
        email="workflow-invalid-open-resolved@example.com",
    )

    response = update_case_status(
        client,
        case["id"],
        "RESOLVED",
        resolution_reason="Should not be accepted.",
    )

    assert response.status_code == 400


def test_open_cannot_transition_directly_to_closed(
    client, create_test_user, cleanup_compliance_cases, cleanup_test_customers
):
    admin = create_test_user(
        email="workflow-invalid-open-closed-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    case = create_compliance_case(
        client,
        email="workflow-invalid-open-closed@example.com",
    )

    response = update_case_status(
        client,
        case["id"],
        "CLOSED",
    )

    assert response.status_code == 400


def test_closed_case_cannot_change_status(
    client, create_test_user, cleanup_compliance_cases, cleanup_test_customers
):
    admin = create_test_user(
        email="workflow-terminal-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    reviewer = create_test_user(
        email="workflow-terminal-reviewer@example.com",
        role=UserRole.REVIEWER,
    )

    authenticate_client(client, admin)

    case = create_compliance_case(
        client,
        email="workflow-terminal-customer@example.com",
    )

    case_id = case["id"]

    assert (
        assign_case(
            client,
            case_id,
            reviewer.id,
        ).status_code
        == 200
    )

    assert (
        update_case_status(
            client,
            case_id,
            "UNDER_REVIEW",
        ).status_code
        == 200
    )

    assert (
        update_case_status(
            client,
            case_id,
            "RESOLVED",
            resolution_reason="Completed review.",
        ).status_code
        == 200
    )

    assert (
        update_case_status(
            client,
            case_id,
            "CLOSED",
        ).status_code
        == 200
    )

    response = update_case_status(
        client,
        case_id,
        "OPEN",
    )

    assert response.status_code == 400


def test_resolving_case_requires_resolution_reason(
    client, create_test_user, cleanup_compliance_cases, cleanup_test_customers
):
    admin = create_test_user(
        email="workflow-reason-required-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    reviewer = create_test_user(
        email="workflow-reason-required-reviewer@example.com",
        role=UserRole.REVIEWER,
    )

    authenticate_client(client, admin)

    case = create_compliance_case(
        client,
        email="workflow-reason-required-customer@example.com",
    )

    assert (
        assign_case(
            client,
            case["id"],
            reviewer.id,
        ).status_code
        == 200
    )

    assert (
        update_case_status(
            client,
            case["id"],
            "UNDER_REVIEW",
        ).status_code
        == 200
    )

    response = update_case_status(
        client,
        case["id"],
        "RESOLVED",
    )

    assert response.status_code == 400


def test_resolving_case_rejects_empty_resolution_reason(
    client, create_test_user, cleanup_compliance_cases, cleanup_test_customers
):
    admin = create_test_user(
        email="workflow-empty-reason-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    reviewer = create_test_user(
        email="workflow-empty-reason-reviewer@example.com",
        role=UserRole.REVIEWER,
    )

    authenticate_client(client, admin)

    case = create_compliance_case(
        client,
        email="workflow-empty-reason-customer@example.com",
    )

    assert (
        assign_case(
            client,
            case["id"],
            reviewer.id,
        ).status_code
        == 200
    )

    assert (
        update_case_status(
            client,
            case["id"],
            "UNDER_REVIEW",
        ).status_code
        == 200
    )

    response = update_case_status(
        client,
        case["id"],
        "RESOLVED",
        resolution_reason="   ",
    )

    assert response.status_code == 400


def test_compliance_case_workflow_history_is_recorded(
    client, create_test_user, cleanup_compliance_cases, cleanup_test_customers
):
    admin = create_test_user(
        email="workflow-history-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    reviewer = create_test_user(
        email="workflow-history-reviewer@example.com",
        role=UserRole.REVIEWER,
    )

    authenticate_client(client, admin)

    case = create_compliance_case(
        client,
        email="workflow-history-customer@example.com",
    )

    case_id = case["id"]

    assert (
        assign_case(
            client,
            case_id,
            reviewer.id,
        ).status_code
        == 200
    )

    assert (
        update_case_status(
            client,
            case_id,
            "UNDER_REVIEW",
        ).status_code
        == 200
    )

    assert (
        update_case_status(
            client,
            case_id,
            "RESOLVED",
            resolution_reason="Review completed.",
        ).status_code
        == 200
    )

    assert (
        update_case_status(
            client,
            case_id,
            "CLOSED",
        ).status_code
        == 200
    )

    response = client.get(f"/api/v1/compliance-cases/{case_id}/history")

    assert response.status_code == 200

    history = response.json()["data"]

    assert len(history) == 4

    assert history[0]["from_status"] == "OPEN"
    assert history[0]["to_status"] == "ASSIGNED"

    assert history[1]["from_status"] == "ASSIGNED"
    assert history[1]["to_status"] == "UNDER_REVIEW"

    assert history[2]["from_status"] == "UNDER_REVIEW"
    assert history[2]["to_status"] == "RESOLVED"

    assert history[2]["reason"] == "Review completed."

    assert history[3]["from_status"] == "RESOLVED"
    assert history[3]["to_status"] == "CLOSED"


def test_invalid_transition_does_not_create_history(
    client, create_test_user, cleanup_compliance_cases, cleanup_test_customers
):
    admin = create_test_user(
        email="workflow-no-history-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    case = create_compliance_case(
        client,
        email="workflow-no-history-customer@example.com",
    )

    case_id = case["id"]

    response = update_case_status(
        client,
        case_id,
        "RESOLVED",
        resolution_reason="Invalid transition.",
    )

    assert response.status_code == 400

    history_response = client.get(f"/api/v1/compliance-cases/{case_id}/history")

    assert history_response.status_code == 200
    assert history_response.json()["data"] == []


def test_compliance_case_status_change_is_audited(
    client,
    create_test_user,
    cleanup_compliance_cases,
    cleanup_test_customers,
    db_session,
):
    admin = create_test_user(
        email="workflow-audit-status-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    reviewer = create_test_user(
        email="workflow-audit-status-reviewer@example.com",
        role=UserRole.REVIEWER,
    )

    authenticate_client(client, admin)

    case = create_compliance_case(
        client,
        email="workflow-audit-status-customer@example.com",
    )

    case_id = case["id"]

    assert (
        assign_case(
            client,
            case_id,
            reviewer.id,
        ).status_code
        == 200
    )

    response = update_case_status(
        client,
        case_id,
        "UNDER_REVIEW",
    )

    assert response.status_code == 200

    audit_log = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.user_id == admin.id,
            AuditLog.event_type == AuditEventType.COMPLIANCE_CASE_STATUS_CHANGED,
            AuditLog.resource_type == "compliance_case",
        )
        .order_by(AuditLog.timestamp.desc())
        .first()
    )

    assert audit_log is not None
    assert audit_log.resource_id is not None
    assert str(audit_log.resource_id) == case_id


def test_compliance_case_assignment_is_audited(
    client,
    create_test_user,
    cleanup_compliance_cases,
    cleanup_test_customers,
    db_session,
):
    admin = create_test_user(
        email="workflow-audit-assignment-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    reviewer = create_test_user(
        email="workflow-audit-assignment-reviewer@example.com",
        role=UserRole.REVIEWER,
    )

    authenticate_client(client, admin)

    case = create_compliance_case(
        client,
        email="workflow-audit-assignment-customer@example.com",
    )

    response = assign_case(
        client,
        case["id"],
        reviewer.id,
    )

    assert response.status_code == 200

    audit_log = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.user_id == admin.id,
            AuditLog.event_type == AuditEventType.COMPLIANCE_CASE_ASSIGNED,
            AuditLog.resource_type == "compliance_case",
        )
        .order_by(AuditLog.timestamp.desc())
        .first()
    )

    assert audit_log is not None
    assert audit_log.resource_id is not None
    assert str(audit_log.resource_id) == case["id"]


def test_compliance_case_cannot_be_assigned_to_unauthorized_user(
    client, create_test_user, cleanup_compliance_cases, cleanup_test_customers
):
    admin = create_test_user(
        email="workflow-invalid-assignee-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    auditor = create_test_user(
        email="workflow-invalid-assignee-auditor@example.com",
        role=UserRole.AUDITOR,
    )

    authenticate_client(client, admin)

    case = create_compliance_case(
        client,
        email="workflow-invalid-assignee-customer@example.com",
    )

    response = assign_case(
        client,
        case["id"],
        auditor.id,
    )

    assert response.status_code == 400


def test_assigning_nonexistent_user_returns_404(
    client, create_test_user, cleanup_compliance_cases, cleanup_test_customers
):
    admin = create_test_user(
        email="workflow-missing-assignee-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    case = create_compliance_case(
        client,
        email="workflow-missing-assignee-customer@example.com",
    )

    response = assign_case(
        client,
        case["id"],
        uuid4(),
    )

    assert response.status_code == 404


def test_update_nonexistent_compliance_case_status_returns_404(
    client, create_test_user, cleanup_compliance_cases, cleanup_test_customers
):
    admin = create_test_user(
        email="workflow-missing-case-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    response = update_case_status(
        client,
        str(uuid4()),
        "ASSIGNED",
    )

    assert response.status_code == 404
