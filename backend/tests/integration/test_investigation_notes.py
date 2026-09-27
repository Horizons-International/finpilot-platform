import uuid
from unittest.mock import MagicMock

from app.models.audit_log import AuditLog
from app.models.investigation_note import InvestigationNote
from app.services.investigation_note_service import (
    InvestigationNoteService,
)
from app.utils.enums import (
    AuditEventType,
    InvestigationNoteType,
    UserRole,
)
from tests.helpers import (
    authenticate_client,
    create_customer_with_data,
    create_verification_case,
)


def create_assigned_case(
    client,
    create_test_user,
):
    manager = create_test_user(
        email=(f"investigation-manager-{uuid.uuid4()}@example.com"),
        role=UserRole.ADMINISTRATOR,
    )

    reviewer = create_test_user(
        email=(f"investigation-reviewer-{uuid.uuid4()}@example.com"),
        role=UserRole.REVIEWER,
    )

    authenticate_client(
        client,
        manager,
    )

    customer_response = create_customer_with_data(
        client,
        email=(f"investigation-customer-{uuid.uuid4()}@example.com"),
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    case = create_verification_case(
        client,
        customer_id,
    )

    case_id = case["id"]

    assignment_response = client.patch(
        f"/api/v1/customers/{customer_id}/verification-cases/{case_id}/assignment",
        json={
            "assigned_to": str(reviewer.id),
        },
    )

    assert assignment_response.status_code == 200

    authenticate_client(
        client,
        reviewer,
    )

    return customer_id, case_id, manager, reviewer


def test_assigned_reviewer_can_add_investigation_note(
    client,
    db_session,
    create_test_user,
    cleanup_test_customers,
    cleanup_investigation_notes,
):
    (
        customer_id,
        case_id,
        _,
        reviewer,
    ) = create_assigned_case(
        client,
        create_test_user,
    )

    response = client.post(
        f"/api/v1/customers/{customer_id}/"
        f"verification-cases/{case_id}/"
        "investigation-notes",
        json={
            "activity_type": "NOTE",
            "note": (
                "Reviewed the submitted identity document against the customer profile."
            ),
        },
    )

    assert response.status_code == 201

    data = response.json()["data"]

    assert data["id"] is not None
    assert data["case_id"] == case_id
    assert data["user_id"] == str(reviewer.id)
    assert data["activity_type"] == "NOTE"
    assert data["note"] == (
        "Reviewed the submitted identity document against the customer profile."
    )
    assert data["attachment_reference"] is None
    assert data["created_at"] is not None

    db_session.expire_all()

    saved_note = (
        db_session.query(InvestigationNote)
        .filter(InvestigationNote.case_id == uuid.UUID(case_id))
        .first()
    )

    assert saved_note is not None
    assert saved_note.user_id == reviewer.id
    assert saved_note.activity_type.value == "NOTE"


def test_reviewer_can_record_investigation_action(
    client,
    create_test_user,
    cleanup_test_customers,
    cleanup_investigation_notes,
):
    customer_id, case_id, _, _ = create_assigned_case(
        client,
        create_test_user,
    )

    response = client.post(
        f"/api/v1/customers/{customer_id}/"
        f"verification-cases/{case_id}/"
        "investigation-notes",
        json={
            "activity_type": "ACTION",
            "note": ("Requested additional bank statements from the customer."),
        },
    )

    assert response.status_code == 201

    data = response.json()["data"]

    assert data["activity_type"] == "ACTION"
    assert data["note"] == ("Requested additional bank statements from the customer.")


def test_reviewer_can_add_resolution_comment(
    client,
    create_test_user,
    cleanup_test_customers,
    cleanup_investigation_notes,
):
    customer_id, case_id, _, _ = create_assigned_case(
        client,
        create_test_user,
    )

    response = client.post(
        f"/api/v1/customers/{customer_id}/"
        f"verification-cases/{case_id}/"
        "investigation-notes",
        json={
            "activity_type": "RESOLUTION",
            "note": (
                "Investigation completed. Evidence was "
                "reviewed and the case can proceed to "
                "final decision."
            ),
        },
    )

    assert response.status_code == 201

    data = response.json()["data"]

    assert data["activity_type"] == "RESOLUTION"


def test_investigation_note_can_reference_supporting_document(
    client,
    db_session,
    create_test_user,
    cleanup_test_customers,
    cleanup_investigation_notes,
):
    customer_id, case_id, _, reviewer = create_assigned_case(
        client,
        create_test_user,
    )

    attachment_reference = f"file-reference-{uuid.uuid4()}"

    response = client.post(
        f"/api/v1/customers/{customer_id}/"
        f"verification-cases/{case_id}/"
        "investigation-notes",
        json={
            "activity_type": "NOTE",
            "note": "Reviewed supporting bank statement.",
            "attachment_reference": attachment_reference,
        },
    )

    assert response.status_code == 201

    data = response.json()["data"]

    assert data["attachment_reference"] == (attachment_reference)

    db_session.expire_all()

    note = (
        db_session.query(InvestigationNote)
        .filter(
            InvestigationNote.case_id == uuid.UUID(case_id),
            InvestigationNote.user_id == reviewer.id,
        )
        .first()
    )

    assert note is not None
    assert note.attachment_reference == (attachment_reference)


def test_investigation_note_history_is_available(
    client,
    create_test_user,
    cleanup_test_customers,
    cleanup_investigation_notes,
):
    customer_id, case_id, _, _ = create_assigned_case(
        client,
        create_test_user,
    )

    first_response = client.post(
        f"/api/v1/customers/{customer_id}/"
        f"verification-cases/{case_id}/"
        "investigation-notes",
        json={
            "activity_type": "NOTE",
            "note": "Initial document review completed.",
        },
    )

    assert first_response.status_code == 201

    second_response = client.post(
        f"/api/v1/customers/{customer_id}/"
        f"verification-cases/{case_id}/"
        "investigation-notes",
        json={
            "activity_type": "ACTION",
            "note": "Customer requested additional evidence.",
        },
    )

    assert second_response.status_code == 201

    third_response = client.post(
        f"/api/v1/customers/{customer_id}/"
        f"verification-cases/{case_id}/"
        "investigation-notes",
        json={
            "activity_type": "RESOLUTION",
            "note": "Supporting evidence was received.",
        },
    )

    assert third_response.status_code == 201

    response = client.get(
        f"/api/v1/customers/{customer_id}/"
        f"verification-cases/{case_id}/"
        "investigation-notes",
    )

    assert response.status_code == 200

    notes = response.json()["data"]

    assert len(notes) == 3

    activity_types = {note["activity_type"] for note in notes}

    assert activity_types == {
        "NOTE",
        "ACTION",
        "RESOLUTION",
    }

    # API returns newest first.
    assert notes[0]["activity_type"] == "RESOLUTION"


def test_reviewer_cannot_add_note_to_another_reviewers_case(
    client,
    create_test_user,
    cleanup_test_customers,
    cleanup_investigation_notes,
):
    (
        customer_id,
        case_id,
        _,
        assigned_reviewer,
    ) = create_assigned_case(
        client,
        create_test_user,
    )

    other_reviewer = create_test_user(
        email=(f"other-investigation-reviewer-{uuid.uuid4()}@example.com"),
        role=UserRole.REVIEWER,
    )

    authenticate_client(
        client,
        other_reviewer,
    )

    response = client.post(
        f"/api/v1/customers/{customer_id}/"
        f"verification-cases/{case_id}/"
        "investigation-notes",
        json={
            "activity_type": "NOTE",
            "note": "This should not be allowed.",
        },
    )

    assert response.status_code == 403

    # Make sure the assignment itself wasn't changed.
    assert assigned_reviewer.id != other_reviewer.id


def test_auditor_cannot_add_investigation_note(
    client,
    create_test_user,
    cleanup_test_customers,
    cleanup_investigation_notes,
):
    manager = create_test_user(
        email=(f"investigation-rbac-manager-{uuid.uuid4()}@example.com"),
        role=UserRole.ADMINISTRATOR,
    )

    reviewer = create_test_user(
        email=(f"investigation-rbac-reviewer-{uuid.uuid4()}@example.com"),
        role=UserRole.REVIEWER,
    )

    auditor = create_test_user(
        email=(f"investigation-rbac-auditor-{uuid.uuid4()}@example.com"),
        role=UserRole.AUDITOR,
    )

    authenticate_client(client, manager)

    customer_response = create_customer_with_data(
        client,
        email=(f"investigation-rbac-customer-{uuid.uuid4()}@example.com"),
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    case = create_verification_case(
        client,
        customer_id,
    )

    case_id = case["id"]

    assignment_response = client.patch(
        f"/api/v1/customers/{customer_id}/verification-cases/{case_id}/assignment",
        json={
            "assigned_to": str(reviewer.id),
        },
    )

    assert assignment_response.status_code == 200

    authenticate_client(
        client,
        auditor,
    )

    response = client.post(
        f"/api/v1/customers/{customer_id}/"
        f"verification-cases/{case_id}/"
        "investigation-notes",
        json={
            "activity_type": "NOTE",
            "note": "Should not be allowed.",
        },
    )

    assert response.status_code == 403


def test_compliance_manager_can_view_investigation_history(
    client,
    create_test_user,
    cleanup_test_customers,
    cleanup_investigation_notes,
):
    (
        customer_id,
        case_id,
        manager,
        reviewer,
    ) = create_assigned_case(
        client,
        create_test_user,
    )

    authenticate_client(
        client,
        reviewer,
    )

    create_response = client.post(
        f"/api/v1/customers/{customer_id}/"
        f"verification-cases/{case_id}/"
        "investigation-notes",
        json={
            "activity_type": "NOTE",
            "note": "Reviewer documented evidence.",
        },
    )

    assert create_response.status_code == 201

    authenticate_client(
        client,
        manager,
    )

    response = client.get(
        f"/api/v1/customers/{customer_id}/"
        f"verification-cases/{case_id}/"
        "investigation-notes",
    )

    assert response.status_code == 200

    notes = response.json()["data"]

    assert len(notes) == 1
    assert notes[0]["user_id"] == str(reviewer.id)


def test_investigation_note_creation_is_audited(
    client,
    db_session,
    create_test_user,
    cleanup_test_customers,
    cleanup_investigation_notes,
):
    (
        customer_id,
        case_id,
        _,
        reviewer,
    ) = create_assigned_case(
        client,
        create_test_user,
    )

    response = client.post(
        f"/api/v1/customers/{customer_id}/"
        f"verification-cases/{case_id}/"
        "investigation-notes",
        json={
            "activity_type": "ACTION",
            "note": "Requested additional evidence.",
        },
    )

    assert response.status_code == 201

    note_id = response.json()["data"]["id"]

    db_session.expire_all()

    audit_log = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.user_id == reviewer.id,
            AuditLog.event_type == AuditEventType.INVESTIGATION_NOTE_CREATED,
            AuditLog.resource_type == "investigation_note",
            AuditLog.resource_id == note_id,
        )
        .order_by(
            AuditLog.timestamp.desc(),
        )
        .first()
    )

    assert audit_log is not None


def test_create_investigation_note_commits_and_audits():
    db = MagicMock()

    service = InvestigationNoteService(db)

    case_id = uuid.uuid4()
    customer_id = uuid.uuid4()
    reviewer_id = uuid.uuid4()

    case = MagicMock()
    case.id = case_id
    case.customer_id = customer_id
    case.assigned_to = reviewer_id

    service.repository = MagicMock()
    service.repository.get_case.return_value = case

    created_note = MagicMock()
    created_note.id = uuid.uuid4()
    created_note.case_id = case_id

    service.repository.create.return_value = created_note

    service.audit_service = MagicMock()

    result = service.create_note(
        customer_id=customer_id,
        case_id=case_id,
        user_id=reviewer_id,
        user_email="reviewer@example.com",
        activity_type=InvestigationNoteType.ACTION,
        note="Requested additional evidence.",
        attachment_reference="file-reference-123",
    )

    assert result is created_note

    service.repository.create.assert_called_once()

    created = service.repository.create.call_args.args[0]

    assert created.case_id == case_id
    assert created.user_id == reviewer_id
    assert created.activity_type == InvestigationNoteType.ACTION
    assert created.note == ("Requested additional evidence.")
    assert created.attachment_reference == ("file-reference-123")

    service.audit_service.log_event.assert_called_once()

    db.commit.assert_called_once()
