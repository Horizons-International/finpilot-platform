from uuid import UUID

from sqlalchemy.orm import Session

from app.models.compliance_case import ComplianceCase
from app.models.compliance_case_history import ComplianceCaseHistory
from app.models.customer import Customer
from app.models.user import User
from app.repositories.compliance_case_history_repository import (
    ComplianceCaseHistoryRepository,
)
from app.repositories.compliance_case_repository import (
    ComplianceCaseRepository,
)
from app.schemas.compliance_case import (
    ComplianceCaseCreate,
    ComplianceCaseUpdate,
)
from app.services.audit_service import AuditService
from app.services.compliance_workflow import compliance_workflow_validator
from app.utils.date_time import utc_now
from app.utils.enums import (
    AuditEventType,
    ComplianceCaseStatus,
    ComplianceCaseType,
    UserRole,
)
from app.utils.errors import bad_request, not_found


class ComplianceService:
    def __init__(self, db: Session) -> None:
        self.db = db

        self.repository = ComplianceCaseRepository(db)

        self.history_repository = ComplianceCaseHistoryRepository(db)

        self.audit_service = AuditService(db)

    # ------------------------------------------------------------------
    # Existing CRUD operations
    # ------------------------------------------------------------------

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

            self._validate_reviewer(assigned_user)

        case = ComplianceCase(
            customer_id=case_data.customer_id,
            case_type=case_data.case_type,
            priority=case_data.priority,
            status=ComplianceCaseStatus.OPEN,
            assigned_to=None,
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

        # If a reviewer was supplied during creation, use the same
        # controlled assignment operation as the assignment endpoint.
        if case_data.assigned_to is not None:
            case = self.assign_case(
                case.id,
                case_data.assigned_to,
                user_id=user_id,
                email=email,
            )

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

        return self.repository.get_by_customer_id(customer_id)

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

            self._validate_reviewer(assigned_user)

        update_data = case_data.model_dump(
            exclude_unset=True,
        )

        for field, value in update_data.items():
            setattr(case, field, value)

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

    # ------------------------------------------------------------------
    # Workflow operations
    # ------------------------------------------------------------------

    def assign_case(
        self,
        case_id: UUID,
        assigned_to: UUID,
        *,
        user_id: UUID,
        email: str,
    ) -> ComplianceCase:
        case = self.get_case(case_id)

        assigned_user = self.db.get(
            User,
            assigned_to,
        )

        if assigned_user is None:
            raise not_found("Assigned user")

        self._validate_reviewer(assigned_user)

        if case.assigned_to == assigned_to:
            raise bad_request("Compliance case is already assigned to this user.")

        previous_status = case.status

        if previous_status == ComplianceCaseStatus.OPEN:
            compliance_workflow_validator.validate_transition(
                previous_status,
                ComplianceCaseStatus.ASSIGNED,
            )

            case.status = ComplianceCaseStatus.ASSIGNED

            self.history_repository.create(
                ComplianceCaseHistory(
                    compliance_case_id=case.id,
                    from_status=previous_status,
                    to_status=ComplianceCaseStatus.ASSIGNED,
                    changed_by=user_id,
                    reason=None,
                )
            )

        case.assigned_to = assigned_to

        self.audit_service.log_event(
            event_type=AuditEventType.COMPLIANCE_CASE_ASSIGNED,
            user_id=user_id,
            email=email,
            resource_type="compliance_case",
            resource_id=case.id,
        )

        self.db.commit()
        self.db.refresh(case)

        return case

    def update_case_status(
        self,
        case_id: UUID,
        new_status: ComplianceCaseStatus,
        *,
        user_id: UUID,
        email: str,
        resolution_reason: str | None = None,
    ) -> ComplianceCase:
        case = self.get_case(case_id)

        previous_status = case.status

        compliance_workflow_validator.validate_transition(
            previous_status,
            new_status,
        )

        if new_status == ComplianceCaseStatus.RESOLVED:
            self._validate_resolution_reason(resolution_reason)

        if new_status == ComplianceCaseStatus.CLOSED:
            if previous_status != ComplianceCaseStatus.RESOLVED:
                # This is technically already protected by the
                # transition map, but keeping the business rule
                # explicit makes the invariant clear.
                raise bad_request("Only a resolved compliance case can be closed.")

        case.status = new_status

        if (
            new_status == ComplianceCaseStatus.RESOLVED
            and resolution_reason is not None
        ):
            case.resolution_reason = resolution_reason.strip()

        if new_status == ComplianceCaseStatus.CLOSED:
            case.closed_at = utc_now()

        history_reason = None

        if (
            new_status == ComplianceCaseStatus.RESOLVED
            and resolution_reason is not None
        ):
            history_reason = resolution_reason.strip()

        self.history_repository.create(
            ComplianceCaseHistory(
                compliance_case_id=case.id,
                from_status=previous_status,
                to_status=new_status,
                changed_by=user_id,
                reason=history_reason,
            )
        )

        self.audit_service.log_event(
            event_type=AuditEventType.COMPLIANCE_CASE_STATUS_CHANGED,
            user_id=user_id,
            email=email,
            resource_type="compliance_case",
            resource_id=case.id,
        )

        self.db.commit()
        self.db.refresh(case)

        return case

    def get_case_history(
        self,
        case_id: UUID,
    ) -> list[ComplianceCaseHistory]:
        # Verify that the case exists before querying history.
        self.get_case(case_id)

        return self.history_repository.get_by_case_id(case_id)

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_resolution_reason(
        resolution_reason: str | None,
    ) -> None:
        if resolution_reason is None:
            raise bad_request(
                "A resolution reason is required when resolving a compliance case."
            )

        if not resolution_reason.strip():
            raise bad_request(
                "A resolution reason is required when resolving a compliance case."
            )

    @staticmethod
    def _validate_reviewer(
        user: User,
    ) -> None:
        allowed_roles = {
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
        }

        if user.role not in allowed_roles:
            raise bad_request(
                "The assigned user is not authorized to review compliance cases."
            )
