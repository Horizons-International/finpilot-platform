from uuid import UUID

from sqlalchemy.orm import Session

from app.models.audit_log import AuditEventType
from app.models.verification_review import VerificationReview
from app.repositories.verification_case_repository import (
    VerificationCaseRepository,
)
from app.repositories.verification_review_repository import (
    VerificationReviewRepository,
)
from app.services.audit_service import AuditService
from app.services.customer_audit_log_service import CustomerAuditLogService
from app.utils.date_time import utc_now
from app.utils.enums import ReviewDecision, VerificationStatus
from app.utils.errors import bad_request, not_found


class VerificationReviewService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.verification_case_repository = VerificationCaseRepository(db)
        self.customer_audit_log_service = CustomerAuditLogService(db)
        self.review_repository = VerificationReviewRepository(db)
        self.audit_service = AuditService(db)

    def start_review(
        self,
        *,
        customer_id: UUID,
        verification_case_id: UUID,
        reviewer_id: UUID,
        email: str,
    ) -> None:
        case = self.verification_case_repository.get_by_id_and_customer_and_reviewer(
            verification_case_id=verification_case_id,
            customer_id=customer_id,
            reviewer_id=reviewer_id,
        )

        if case is None:
            raise not_found("Verification case")

        if case.status != VerificationStatus.PENDING:
            raise bad_request(
                "Verification case cannot be started for review in its current status."
            )

        old_status = case.status
        new_status = VerificationStatus.UNDER_REVIEW

        try:
            case.status = new_status
            self.verification_case_repository.update(case)

            self.audit_service.log_event(
                event_type=AuditEventType.VERIFICATION_CASE_STATUS_CHANGED,
                user_id=reviewer_id,
                email=email,
                resource_type="verification_case",
                resource_id=verification_case_id,
            )

            self.customer_audit_log_service.create_audit_log(
                customer_id=case.customer_id,
                user_id=reviewer_id,
                resource_type="verification_case",
                resource_id=verification_case_id,
                action="START VERIFICATION REVIEW",
                old_value={
                    "status": old_status.value,
                },
                new_value={
                    "status": new_status.value,
                },
            )

            self.db.commit()

        except Exception:
            self.db.rollback()
            raise

    def create_review(
        self,
        *,
        customer_id: UUID,
        verification_case_id: UUID,
        reviewer_id: UUID,
        email: str,
        decision: ReviewDecision,
        notes: str | None,
    ) -> VerificationReview:
        case = self.verification_case_repository.get_by_id_and_customer_and_reviewer(
            verification_case_id=verification_case_id,
            customer_id=customer_id,
            reviewer_id=reviewer_id,
        )

        if case is None:
            raise not_found("Verification case")

        if case.status != VerificationStatus.UNDER_REVIEW:
            raise bad_request(
                "Verification case must be under review before a decision can be made."
            )

        if decision == ReviewDecision.APPROVE:
            new_status = VerificationStatus.APPROVED

        elif decision == ReviewDecision.REJECT:
            new_status = VerificationStatus.REJECTED

        elif decision == ReviewDecision.REQUEST_MORE_INFORMATION:
            new_status = VerificationStatus.PENDING

        else:
            raise bad_request("Invalid review decision.")

        old_status = case.status

        review = VerificationReview(
            verification_case_id=verification_case_id,
            reviewer_id=reviewer_id,
            decision=decision,
            notes=notes,
        )

        try:
            self.review_repository.create(review)

            case.status = new_status

            if new_status in {
                VerificationStatus.APPROVED,
                VerificationStatus.REJECTED,
            }:
                case.completed_at = utc_now()

            self.verification_case_repository.update(case)

            self.audit_service.log_event(
                event_type=AuditEventType.VERIFICATION_CASE_STATUS_CHANGED,
                user_id=reviewer_id,
                email=email,
                resource_type="verification_case",
                resource_id=verification_case_id,
            )

            self.customer_audit_log_service.create_audit_log(
                customer_id=case.customer_id,
                user_id=reviewer_id,
                resource_type="verification_case",
                resource_id=verification_case_id,
                action="REVIEW VERIFICATION CASE",
                old_value={
                    "status": old_status.value,
                },
                new_value={
                    "status": new_status.value,
                    "decision": decision.value,
                    "notes": notes,
                },
            )

            self.db.commit()
            self.db.refresh(review)

            return review

        except Exception:
            self.db.rollback()
            raise
