from uuid import UUID

from sqlalchemy.orm import Session

from app.models.compliance_case import ComplianceCase
from app.models.customer import Customer
from app.models.user import User
from app.repositories.compliance_case_repository import (
    ComplianceCaseRepository,
)
from app.schemas.compliance_case import (
    ComplianceCaseCreate,
    ComplianceCaseUpdate,
)
from app.services.audit_service import AuditService
from app.utils.date_time import utc_now
from app.utils.enums import (
    AuditEventType,
    ComplianceCaseStatus,
    ComplianceCaseType,
)
from app.utils.errors import not_found


class ComplianceService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = ComplianceCaseRepository(db)
        self.audit_service = AuditService(db)

    def create_case(
        self,
        case_data: ComplianceCaseCreate,
        *,
        user_id: UUID,
        email: str,
    ) -> ComplianceCase:
        customer = self.db.get(
            Customer,
            case_data.customer_id,
        )

        if customer is None:
            raise not_found("Customer")

        if case_data.assigned_to is not None:
            assigned_user = self.db.get(
                User,
                case_data.assigned_to,
            )

            if assigned_user is None:
                raise not_found("Assigned user")

        case = ComplianceCase(
            customer_id=case_data.customer_id,
            case_type=case_data.case_type,
            priority=case_data.priority,
            status=ComplianceCaseStatus.OPEN,
            assigned_to=case_data.assigned_to,
            description=case_data.description,
        )

        case = self.repository.create(case)

        self.audit_service.log_event(
            event_type=AuditEventType.COMPLIANCE_CASE_CREATED,
            user_id=user_id,
            email=email,
            resource_type="compliance_case",
            resource_id=case.id,
        )

        self.db.commit()
        self.db.refresh(case)

        return case

    def get_case(
        self,
        case_id: UUID,
    ) -> ComplianceCase:
        case = self.repository.get_by_id(case_id)

        if case is None:
            raise not_found("Compliance case")

        return case

    def get_cases_by_customer(
        self,
        customer_id: UUID,
    ) -> list[ComplianceCase]:
        customer = self.db.get(
            Customer,
            customer_id,
        )

        if customer is None:
            raise not_found("Customer")

        return self.repository.get_by_customer_id(
            customer_id,
        )

    def get_cases(
        self,
        *,
        status: ComplianceCaseStatus | None = None,
        case_type: ComplianceCaseType | None = None,
        assigned_to: UUID | None = None,
    ) -> list[ComplianceCase]:
        return self.repository.get_all(
            status=status,
            case_type=case_type,
            assigned_to=assigned_to,
        )

    def update_case(
        self,
        case_id: UUID,
        case_data: ComplianceCaseUpdate,
        *,
        user_id: UUID,
        email: str,
    ) -> ComplianceCase:
        case = self.get_case(case_id)

        if case_data.assigned_to is not None:
            assigned_user = self.db.get(
                User,
                case_data.assigned_to,
            )

            if assigned_user is None:
                raise not_found("Assigned user")

        update_data = case_data.model_dump(
            exclude_unset=True,
        )

        for field, value in update_data.items():
            setattr(case, field, value)

        if case.status == ComplianceCaseStatus.CLOSED:
            if case.closed_at is None:
                case.closed_at = utc_now()
        else:
            case.closed_at = None

        case = self.repository.update(case)

        self.audit_service.log_event(
            event_type=AuditEventType.COMPLIANCE_CASE_UPDATED,
            user_id=user_id,
            email=email,
            resource_type="compliance_case",
            resource_id=case.id,
        )

        self.db.commit()
        self.db.refresh(case)

        return case
