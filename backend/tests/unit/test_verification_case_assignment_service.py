from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from app.services.verification_case_assignment_service import (
    VerificationCaseAssignmentService,
)
from app.utils.enums import (
    UserRole,
    UserStatus,
)


def test_assign_case_creates_history_and_commits():
    db = MagicMock()

    case_id = uuid4()
    customer_id = uuid4()
    manager_id = uuid4()
    reviewer_id = uuid4()

    case = SimpleNamespace(
        id=case_id,
        customer_id=customer_id,
        assigned_to=None,
        assigned_at=None,
        assigned_by=None,
    )

    reviewer = SimpleNamespace(
        id=reviewer_id,
        role=UserRole.REVIEWER,
        status=UserStatus.ACTIVE,
        is_deleted=False,
    )

    repository = MagicMock()

    repository.get_case_for_update.return_value = case
    repository.get_reviewer.return_value = reviewer

    history = SimpleNamespace(
        verification_case_id=case_id,
        assigned_to=reviewer_id,
        previous_reviewer=None,
        assigned_by=manager_id,
        assigned_at=None,
    )

    repository.create_history.return_value = history

    service = VerificationCaseAssignmentService(db)

    service.repository = repository
    service.audit_service = MagicMock()

    result = service.assign_case(
        customer_id=customer_id,
        verification_case_id=case_id,
        reviewer_id=reviewer_id,
        assigned_by=manager_id,
        assigned_by_email="manager@example.com",
    )

    assert result is history

    assert case.assigned_to == reviewer_id
    assert case.assigned_by == manager_id
    assert case.assigned_at is not None

    repository.assign_case.assert_called_once_with(case)
    repository.create_history.assert_called_once()

    service.audit_service.log_event.assert_called_once()

    db.commit.assert_called_once()
