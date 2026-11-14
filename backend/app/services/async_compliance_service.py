"""Async compliance case management and audit workflow service."""

from typing import NoReturn
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.compliance_case import ComplianceCase
from app.models.compliance_case_history import ComplianceCaseHistory
from app.models.customer import Customer
from app.models.user import User
from app.repositories.async_compliance_case_repository import (
    AsyncComplianceCaseHistoryRepository,
    AsyncComplianceCaseRepository,
)
from app.schemas.compliance_case import ComplianceCaseCreate, ComplianceCaseUpdate
from app.services.async_audit_service import AsyncAuditService
from app.services.async_notification_service import AsyncNotificationService
from app.services.case_priority_service import CasePriorityService
from app.services.compliance_workflow import compliance_workflow_validator
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


class AsyncComplianceService:
    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.db.info["tenant_id"] = tenant_id
        self.repository = AsyncComplianceCaseRepository(db, tenant_id)
        self.history_repository = AsyncComplianceCaseHistoryRepository(db, tenant_id)
        self.audit_service = AsyncAuditService(db)

    async def _get_tenant_user(self, user_id: UUID) -> User:
        user = await self.db.scalar(
            select(User).where(
                User.id == user_id,
                User.tenant_id == self.tenant_id,
            )
        )
        if user is None:
            await self.audit_service.log_access_denied(
                resource_type="user",
                resource_id=user_id,
                user_id=self.db.info.get("tenant_user_id"),
                email=self.db.info.get("tenant_user_email"),
                ip_address=self.db.info.get("tenant_ip_address"),
                user_agent=self.db.info.get("tenant_user_agent"),
            )
            raise not_found("Assigned user")
        return user

    async def _require_customer(self, customer_id: UUID) -> Customer:
        customer = await self.db.scalar(
            select(Customer).where(
                Customer.id == customer_id,
                Customer.tenant_id == self.tenant_id,
            )
        )
        if customer is None:
            await self.audit_service.log_access_denied(
                resource_type="customer",
                resource_id=customer_id,
                user_id=self.db.info.get("tenant_user_id"),
                email=self.db.info.get("tenant_user_email"),
                ip_address=self.db.info.get("tenant_ip_address"),
                user_agent=self.db.info.get("tenant_user_agent"),
            )
            raise not_found("Customer")
        return customer

    async def _deny_case(self, case_id: UUID) -> NoReturn:
        await self.audit_service.log_access_denied(
            resource_type="compliance_case",
            resource_id=case_id,
            user_id=self.db.info.get("tenant_user_id"),
            email=self.db.info.get("tenant_user_email"),
            ip_address=self.db.info.get("tenant_ip_address"),
            user_agent=self.db.info.get("tenant_user_agent"),
        )
        raise not_found("Compliance case")

    async def _notify(
        self,
        *,
        user_id: UUID,
        title: str,
        message: str,
        event_type: NotificationEventType,
        case_id: UUID,
    ) -> None:
        await AsyncNotificationService(self.db, self.tenant_id).create_notification(
            user_id=user_id,
            title=title,
            message=message,
            event_type=event_type,
            resource_type="compliance_case",
            resource_id=case_id,
            channels=(NotificationChannel.IN_APP,),
        )

    async def _enqueue_webhook(self, event_type: str, case: ComplianceCase) -> None:
        from app.webhooks.async_events import enqueue_webhook_event_async

        await enqueue_webhook_event_async(
            self.db,
            tenant_id=self.tenant_id,
            event_type=event_type,
            data={"case_id": str(case.id), "status": case.status.value},
        )

    async def _refresh_case_priority(self, case_id: UUID) -> None:
        await self.db.run_sync(
            lambda sync_db: CasePriorityService(
                sync_db, tenant_id=self.tenant_id
            ).prioritize_case(case_id)
        )

    async def create_case(
        self,
        case_data: ComplianceCaseCreate,
        *,
        user_id: UUID,
        email: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> ComplianceCase:
        await self._require_customer(case_data.customer_id)
        if case_data.assigned_to is not None:
            assigned_user = await self._get_tenant_user(case_data.assigned_to)
            self._validate_reviewer(assigned_user)

        case = await self.repository.create(
            ComplianceCase(
                tenant_id=self.tenant_id,
                customer_id=case_data.customer_id,
                case_type=case_data.case_type,
                priority=case_data.priority,
                status=ComplianceCaseStatus.OPEN,
                assigned_to=None,
                description=case_data.description,
            )
        )
        await self.audit_service.log_event(
            event_type=AuditEventType.COMPLIANCE_CASE_CREATED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="compliance_case",
            resource_id=case.id,
        )
        await self._enqueue_webhook("case.created", case)
        await self.db.commit()
        await self.db.refresh(case)
        if case_data.assigned_to is not None:
            case = await self.assign_case(
                case.id,
                case_data.assigned_to,
                user_id=user_id,
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
            )
        await self._refresh_case_priority(case.id)
        return case

    async def get_case(self, case_id: UUID) -> ComplianceCase:
        case = await self.repository.get_by_id(case_id)
        if case is None:
            await self._deny_case(case_id)
        return case

    async def get_cases_by_customer(self, customer_id: UUID) -> list[ComplianceCase]:
        await self._require_customer(customer_id)
        return await self.repository.get_by_customer_id(customer_id)

    async def get_cases(
        self,
        *,
        status: ComplianceCaseStatus | None = None,
        case_type: ComplianceCaseType | None = None,
        assigned_to: UUID | None = None,
    ) -> list[ComplianceCase]:
        return await self.repository.get_all(
            status=status,
            case_type=case_type,
            assigned_to=assigned_to,
        )

    async def update_case(
        self,
        case_id: UUID,
        case_data: ComplianceCaseUpdate,
        *,
        user_id: UUID,
        email: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> ComplianceCase:
        case = await self.get_case(case_id)
        if case_data.assigned_to is not None:
            assigned_user = await self._get_tenant_user(case_data.assigned_to)
            self._validate_reviewer(assigned_user)
        for field, value in case_data.model_dump(exclude_unset=True).items():
            setattr(case, field, value)
        case = await self.repository.update(case)
        await self.audit_service.log_event(
            event_type=AuditEventType.COMPLIANCE_CASE_UPDATED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="compliance_case",
            resource_id=case.id,
        )
        if case.assigned_to is not None:
            await self._notify(
                user_id=case.assigned_to,
                title="Compliance case updated",
                message=f"Compliance case {case.id} has been updated.",
                event_type=NotificationEventType.COMPLIANCE_CASE_UPDATED,
                case_id=case.id,
            )
        await self.db.commit()
        await self.db.refresh(case)
        await self._refresh_case_priority(case.id)
        return case

    async def assign_case(
        self,
        case_id: UUID,
        assigned_to: UUID,
        *,
        user_id: UUID,
        email: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> ComplianceCase:
        case = await self.get_case(case_id)
        assigned_user = await self._get_tenant_user(assigned_to)
        self._validate_reviewer(assigned_user)
        if case.assigned_to == assigned_to:
            raise bad_request("Compliance case is already assigned to this user.")

        previous_status = case.status
        if previous_status == ComplianceCaseStatus.OPEN:
            compliance_workflow_validator.validate_transition(
                previous_status, ComplianceCaseStatus.ASSIGNED
            )
            case.status = ComplianceCaseStatus.ASSIGNED
            await self.history_repository.create(
                ComplianceCaseHistory(
                    tenant_id=self.tenant_id,
                    compliance_case_id=case.id,
                    from_status=previous_status,
                    to_status=ComplianceCaseStatus.ASSIGNED,
                    changed_by=user_id,
                    reason=None,
                )
            )
        case.assigned_to = assigned_to
        await self.repository.update(case)
        await self.audit_service.log_event(
            event_type=AuditEventType.COMPLIANCE_CASE_ASSIGNED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="compliance_case",
            resource_id=case.id,
        )
        await self._notify(
            user_id=assigned_to,
            title="Compliance case assigned",
            message=f"Compliance case {case.id} has been assigned to you.",
            event_type=NotificationEventType.COMPLIANCE_CASE_ASSIGNED,
            case_id=case.id,
        )
        await self.db.commit()
        await self.db.refresh(case)
        await self._refresh_case_priority(case.id)
        return case

    async def update_case_status(
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
        case = await self.get_case(case_id)
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
            await self._enqueue_webhook("case.closed", case)

        history_reason = (
            resolution_reason.strip()
            if new_status == ComplianceCaseStatus.RESOLVED
            and resolution_reason is not None
            else None
        )
        await self.history_repository.create(
            ComplianceCaseHistory(
                tenant_id=self.tenant_id,
                compliance_case_id=case.id,
                from_status=previous_status,
                to_status=new_status,
                changed_by=user_id,
                reason=history_reason,
            )
        )
        await self.repository.update(case)
        await self.audit_service.log_event(
            event_type=AuditEventType.COMPLIANCE_CASE_STATUS_CHANGED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="compliance_case",
            resource_id=case.id,
        )
        if case.assigned_to is not None:
            await self._notify(
                user_id=case.assigned_to,
                title="Compliance case updated",
                message=f"Your compliance case has been updated to {new_status.value}.",
                event_type=NotificationEventType.COMPLIANCE_CASE_UPDATED,
                case_id=case.id,
            )
        await self.db.commit()
        await self.db.refresh(case)
        await self._refresh_case_priority(case.id)
        return case

    async def get_case_history(self, case_id: UUID) -> list[ComplianceCaseHistory]:
        await self.get_case(case_id)
        return await self.history_repository.get_by_case_id(case_id)

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
