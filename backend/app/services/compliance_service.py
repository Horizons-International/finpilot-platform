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
from app.services.notification_service import NotificationService
from app.services.tenant_access_audit import deny_tenant_access
from app.utils.date_time import utc_now
from app.utils.enums import (
    AuditEventType,
    ComplianceCaseStatus,
    ComplianceCaseType,
    NotificationChannel,
    NotificationEventType,
    UserRole,
)
from app.utils.errors import bad_request, not_found
from app.webhooks.events import enqueue_webhook_event


class ComplianceService:
    def __init__(self, db: Session, tenant_id: UUID) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.repository = ComplianceCaseRepository(
            db=db,
            tenant_id=tenant_id,
        )
        self.history_repository = ComplianceCaseHistoryRepository(
            db,
            self.tenant_id,
        )
        self.audit_service = AuditService(db)
        self.notification_service = NotificationService(db, self.tenant_id)

    def _refresh_case_priority(self, case_id: UUID) -> None:
        """Keep the priority snapshot current after case mutations.

        Imported locally to avoid coupling the normal CRUD module to scoring
        implementation details at module import time.
        """
        from sqlalchemy.orm import Session as SQLAlchemySession

        session_info = getattr(self.db, "info", None)
        # Some unit tests use lightweight session mocks. Real SQLAlchemy sessions
        # are prioritized automatically; API reads/listing still refresh the score.
        if not isinstance(self.db, SQLAlchemySession) or not isinstance(
            session_info, dict
        ):
            return
        active_tenant_id = session_info.get("tenant_id")
        if active_tenant_id is None:
            session_info["tenant_id"] = self.tenant_id
        elif active_tenant_id != self.tenant_id:
            raise ValueError("Cannot prioritize a compliance case for another tenant.")

        from app.services.case_priority_service import CasePriorityService

        CasePriorityService(self.db, tenant_id=self.tenant_id).prioritize_case(case_id)

    def _get_tenant_user(self, user_id: UUID) -> User:
        user = (
            self.db.query(User)
            .filter(User.id == user_id, User.tenant_id == self.tenant_id)
            .first()
        )
        if user is None:
            deny_tenant_access(
                self.db,
                resource_type="user",
                resource_id=user_id,
                resource_name="Assigned user",
            )
        return user

    def create_case(
        self,
        case_data: ComplianceCaseCreate,
        *,
        user_id: UUID,
        email: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> ComplianceCase:
        customer = (
            self.db.query(Customer)
            .filter(
                Customer.id == case_data.customer_id,
                Customer.tenant_id == self.tenant_id,
            )
            .first()
        )
        if customer is None:
            deny_tenant_access(
                self.db,
                resource_type="customer",
                resource_id=case_data.customer_id,
                resource_name="Customer",
            )

        if case_data.assigned_to is not None:
            assigned_user = self._get_tenant_user(case_data.assigned_to)
            if assigned_user is None:
                raise not_found("Assigned user")
            self._validate_reviewer(assigned_user)

        case = ComplianceCase(
            tenant_id=self.tenant_id,
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
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="compliance_case",
            resource_id=case.id,
        )
        enqueue_webhook_event(
            self.db,
            tenant_id=self.tenant_id,
            event_type="case.created",
            data={"case_id": str(case.id), "status": case.status.value},
        )
        self.db.commit()
        self.db.refresh(case)

        if case_data.assigned_to is not None:
            case = self.assign_case(
                case.id,
                case_data.assigned_to,
                user_id=user_id,
                email=email,
            )

        self._refresh_case_priority(case.id)
        return case

    def get_case(self, case_id: UUID) -> ComplianceCase:
        case = self.repository.get_by_id(case_id)
        if case is None:
            deny_tenant_access(
                self.db,
                resource_type="compliance_case",
                resource_id=case_id,
                resource_name="Compliance case",
            )
        return case

    def get_cases_by_customer(self, customer_id: UUID) -> list[ComplianceCase]:
        customer = (
            self.db.query(Customer)
            .filter(
                Customer.id == customer_id,
                Customer.tenant_id == self.tenant_id,
            )
            .first()
        )
        if customer is None:
            deny_tenant_access(
                self.db,
                resource_type="customer",
                resource_id=customer_id,
                resource_name="Customer",
            )
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
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> ComplianceCase:
        case = self.get_case(case_id)
        if case_data.assigned_to is not None:
            assigned_user = self._get_tenant_user(case_data.assigned_to)
            if assigned_user is None:
                raise not_found("Assigned user")
            self._validate_reviewer(assigned_user)

        update_data = case_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(case, field, value)
        case = self.repository.update(case)

        self.audit_service.log_event(
            event_type=AuditEventType.COMPLIANCE_CASE_UPDATED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="compliance_case",
            resource_id=case.id,
        )
        if case.assigned_to is not None:
            self.notification_service.create_notification(
                user_id=case.assigned_to,
                title="Compliance case updated",
                message=f"Compliance case {case.id} has been updated.",
                event_type=NotificationEventType.COMPLIANCE_CASE_UPDATED,
                resource_type="compliance_case",
                resource_id=case.id,
                channels=(NotificationChannel.IN_APP,),
            )

        self.db.commit()
        self.db.refresh(case)
        self._refresh_case_priority(case.id)
        return case

    def assign_case(
        self,
        case_id: UUID,
        assigned_to: UUID,
        *,
        user_id: UUID,
        email: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> ComplianceCase:
        case = self.get_case(case_id)
        assigned_user = self._get_tenant_user(assigned_to)
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
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="compliance_case",
            resource_id=case.id,
        )
        self.notification_service.create_notification(
            user_id=assigned_to,
            title="Compliance case assigned",
            message=f"Compliance case {case.id} has been assigned to you.",
            event_type=NotificationEventType.COMPLIANCE_CASE_ASSIGNED,
            resource_type="compliance_case",
            resource_id=case.id,
            channels=(NotificationChannel.IN_APP,),
        )
        self.db.commit()
        self.db.refresh(case)
        self._refresh_case_priority(case.id)
        return case

    def update_case_status(
        self,
        case_id: UUID,
        new_status: ComplianceCaseStatus,
        *,
        user_id: UUID,
        email: str,
        resolution_reason: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> ComplianceCase:
        case = self.get_case(case_id)
        previous_status = case.status
        compliance_workflow_validator.validate_transition(previous_status, new_status)

        if new_status == ComplianceCaseStatus.RESOLVED:
            self._validate_resolution_reason(resolution_reason)
        if (
            new_status == ComplianceCaseStatus.CLOSED
            and previous_status != ComplianceCaseStatus.RESOLVED
        ):
            raise bad_request("Only a resolved compliance case can be closed.")

        case.status = new_status
        if (
            new_status == ComplianceCaseStatus.RESOLVED
            and resolution_reason is not None
        ):
            case.resolution_reason = resolution_reason.strip()
        if new_status == ComplianceCaseStatus.CLOSED:
            case.closed_at = utc_now()
            enqueue_webhook_event(
                self.db,
                tenant_id=self.tenant_id,
                event_type="case.closed",
                data={"case_id": str(case.id), "status": new_status.value},
            )

        history_reason = (
            resolution_reason.strip()
            if (
                new_status == ComplianceCaseStatus.RESOLVED
                and resolution_reason is not None
            )
            else None
        )
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
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="compliance_case",
            resource_id=case.id,
        )
        if case.assigned_to is not None:
            self.notification_service.create_notification(
                user_id=case.assigned_to,
                title="Compliance case updated",
                message=f"Your compliance case has been updated to {new_status.value}.",
                event_type=NotificationEventType.COMPLIANCE_CASE_UPDATED,
                resource_type="compliance_case",
                resource_id=case.id,
                channels=(NotificationChannel.IN_APP,),
            )
        self.db.commit()
        self.db.refresh(case)
        self._refresh_case_priority(case.id)
        return case

    def get_case_history(self, case_id: UUID) -> list[ComplianceCaseHistory]:
        self.get_case(case_id)
        return self.history_repository.get_by_case_id(case_id)

    @staticmethod
    def _validate_resolution_reason(resolution_reason: str | None) -> None:
        if resolution_reason is None or not resolution_reason.strip():
            raise bad_request(
                "A resolution reason is required when resolving a compliance case."
            )

    @staticmethod
    def _validate_reviewer(user: User) -> None:
        allowed_roles = {
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
        }
        if user.role not in allowed_roles:
            raise bad_request(
                "The assigned user is not authorized to review compliance cases."
            )
