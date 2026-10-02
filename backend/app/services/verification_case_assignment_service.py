from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.verification_case import IdentityVerificationCase
from app.models.verification_case_assignment_history import (
    VerificationCaseAssignmentHistory,
)
from app.repositories.verification_case_assignment_repository import (
    VerificationCaseAssignmentRepository,
)
from app.services.audit_service import AuditService
from app.services.notification_service import NotificationService
from app.utils.enums import (
    AuditEventType,
    NotificationChannel,
    NotificationEventType,
    UserRole,
    UserStatus,
)
from app.utils.errors import (
    bad_request,
    not_found,
)


class VerificationCaseAssignmentService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = VerificationCaseAssignmentRepository(db)
        self.audit_service = AuditService(db)
        self.notification_service = NotificationService(db)

    def assign_case(
        self,
        *,
        customer_id: UUID,
        verification_case_id: UUID,
        reviewer_id: UUID,
        assigned_by: UUID,
        assigned_by_email: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> VerificationCaseAssignmentHistory:
        case = self.repository.get_case_for_update(
            customer_id=customer_id,
            verification_case_id=verification_case_id,
        )

        if case is None:
            raise not_found("Verification case")

        reviewer = self.repository.get_reviewer(
            reviewer_id,
        )

        if reviewer is None:
            raise not_found("Reviewer")

        if reviewer.role != UserRole.REVIEWER:
            raise bad_request(
                "The selected user is not a reviewer.",
            )

        if reviewer.status != UserStatus.ACTIVE:
            raise bad_request(
                "The selected reviewer is not active.",
            )

        if reviewer.is_deleted:
            raise bad_request(
                "The selected reviewer has been deleted.",
            )

        previous_reviewer = case.assigned_to

        if previous_reviewer == reviewer_id:
            raise bad_request(
                "The verification case is already assigned to this reviewer.",
            )

        assigned_at = datetime.now(timezone.utc)

        case.assigned_to = reviewer_id
        case.assigned_at = assigned_at
        case.assigned_by = assigned_by

        self.repository.assign_case(case)

        history = VerificationCaseAssignmentHistory(
            verification_case_id=case.id,
            assigned_to=reviewer_id,
            previous_reviewer=previous_reviewer,
            assigned_by=assigned_by,
            assigned_at=assigned_at,
        )

        history = self.repository.create_history(history)

        self.audit_service.log_event(
            user_id=assigned_by,
            email=assigned_by_email,
            event_type=AuditEventType.VERIFICATION_CASE_ASSIGNED,
            resource_type="verification_case",
            resource_id=case.id,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        self.notification_service.create_notification(
            user_id=case.assigned_to,
            title="Verification case assigned",
            message=(f"Verification case {case.id} has been assigned."),
            event_type=NotificationEventType.VERIFICATION_CASE_ASSIGNED,
            resource_type="verification_case",
            resource_id=case.id,
            channels=(NotificationChannel.IN_APP,),
        )

        self.db.commit()

        return history

    def get_assignment_history(
        self,
        *,
        customer_id: UUID,
        verification_case_id: UUID,
    ) -> list[VerificationCaseAssignmentHistory]:
        case = self.repository.get_case(
            customer_id=customer_id,
            verification_case_id=verification_case_id,
        )

        if case is None:
            raise not_found("Verification case")

        return self.repository.get_history(
            verification_case_id=verification_case_id,
        )

    def get_assigned_cases(
        self,
        reviewer_id: UUID,
    ):
        return self.repository.get_assigned_cases(
            reviewer_id,
        )

    def get_all_assigned_cases(
        self,
    ) -> list[IdentityVerificationCase]:
        return self.repository.get_all_assigned_cases()
