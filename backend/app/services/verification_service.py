from uuid import UUID

from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.customer_audit_log import CustomerAuditLog
from app.models.verification_case import IdentityVerificationCase
from app.repositories.verification_case_repository import (
    VerificationCaseRepository,
)
from app.schemas.verification_case import (
    VerificationCaseCreate,
    VerificationCaseStatusUpdate,
)
from app.services.audit_service import AuditService
from app.services.workflow_service import WorkflowValidationService
from app.utils.date_time import utc_now
from app.utils.enums import AuditEventType, VerificationStatus
from app.utils.errors import not_found

VERIFICATION_STATUS_TRANSITIONS: dict[
    VerificationStatus,
    set[VerificationStatus],
] = {
    VerificationStatus.NOT_STARTED: {
        VerificationStatus.PENDING,
    },
    VerificationStatus.PENDING: {
        VerificationStatus.UNDER_REVIEW,
    },
    VerificationStatus.UNDER_REVIEW: {
        VerificationStatus.APPROVED,
        VerificationStatus.REJECTED,
    },
    VerificationStatus.APPROVED: set(),
    VerificationStatus.REJECTED: set(),
    VerificationStatus.EXPIRED: set(),
}


class VerificationService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.audit_service = AuditService(db)
        self.repository = VerificationCaseRepository(db)
        self.workflow_service = WorkflowValidationService(
            VERIFICATION_STATUS_TRANSITIONS
        )

    def create_case(
        self,
        customer_id: UUID,
        case_data: VerificationCaseCreate,
        user_id: UUID,
        email: str,
    ) -> IdentityVerificationCase:
        customer = self.db.query(Customer).filter(Customer.id == customer_id).first()

        if customer is None:
            raise not_found("Customer")

        case = IdentityVerificationCase(
            customer_id=customer_id,
            verification_type=case_data.verification_type,
            status=VerificationStatus.NOT_STARTED,
        )

        case = self.repository.create(case)

        self.audit_service.log_event(
            event_type=AuditEventType.VERIFICATION_CASE_CREATED,
            user_id=user_id,
            email=email,
            resource_type="verification_case",
            resource_id=case.id,
        )

        customer_audit_log = CustomerAuditLog(
            customer_id=customer_id,
            user_id=user_id,
            resource_type="verification_case",
            resource_id=case.id,
            action="CREATE VERIFICATION CASE",
            old_value=None,
            new_value={
                "customer_id": str(customer_id),
                "verification_type": case.verification_type.value,
                "status": case.status.value,
            },
        )

        self.db.add(customer_audit_log)
        self.db.flush()

        self.db.commit()
        self.db.refresh(case)

        return case

    def get_cases_by_customer(
        self,
        customer_id: UUID,
    ) -> list[IdentityVerificationCase]:
        customer = self.db.query(Customer).filter(Customer.id == customer_id).first()

        if customer is None:
            raise not_found("Customer")

        return self.repository.get_by_customer_id(customer_id)

    def update_status(
        self,
        customer_id: UUID,
        case_id: UUID,
        status_data: VerificationCaseStatusUpdate,
        user_id: UUID,
        email: str,
    ) -> IdentityVerificationCase:
        customer = self.db.query(Customer).filter(Customer.id == customer_id).first()

        if customer is None:
            raise not_found("Customer")

        case = (
            self.db.query(IdentityVerificationCase)
            .filter(
                IdentityVerificationCase.id == case_id,
                IdentityVerificationCase.customer_id == customer_id,
            )
            .first()
        )

        if case is None:
            raise not_found("Verification case")

        current_status = case.status
        new_status = status_data.status

        self.workflow_service.validate_transition(
            current_status=current_status,
            new_status=new_status,
        )

        case.status = new_status

        if new_status in {
            VerificationStatus.APPROVED,
            VerificationStatus.REJECTED,
        }:
            case.completed_at = utc_now()

        case = self.repository.update(case)

        self.audit_service.log_event(
            event_type=AuditEventType.VERIFICATION_CASE_STATUS_CHANGED,
            user_id=user_id,
            email=email,
            resource_type="verification_case",
            resource_id=case.id,
        )

        customer_audit_log = CustomerAuditLog(
            customer_id=customer_id,
            user_id=user_id,
            resource_type="verification_case",
            resource_id=case.id,
            action="UPDATE VERIFICATION STATUS",
            old_value={
                "status": current_status.value,
            },
            new_value={
                "status": new_status.value,
            },
        )

        self.db.add(customer_audit_log)
        self.db.flush()

        self.db.commit()
        self.db.refresh(case)

        return case
