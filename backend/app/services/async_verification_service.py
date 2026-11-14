"""Async identity-verification case lifecycle service."""

from typing import NoReturn
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.models.customer import Customer
from app.models.customer_audit_log import CustomerAuditLog
from app.models.verification_case import IdentityVerificationCase
from app.providers.factory import get_verification_provider
from app.providers.schemas import VerificationRequest, VerificationResponse
from app.providers.verification_provider import VerificationProvider
from app.repositories.async_verification_case_repository import (
    AsyncVerificationCaseRepository,
)
from app.schemas.verification_case import (
    VerificationCaseCreate,
    VerificationCaseInitiation,
    VerificationCaseStatusUpdate,
)
from app.services.async_audit_service import AsyncAuditService
from app.services.async_notification_service import AsyncNotificationService
from app.services.async_subscription_service import record_subscription_usage
from app.services.workflow_validation_service import WorkflowValidationService
from app.utils.audit import serialize_audit_value
from app.utils.date_time import utc_now
from app.utils.enums import (
    AuditEventType,
    NotificationChannel,
    NotificationEventType,
    VerificationStatus,
)
from app.utils.errors import bad_request, not_found

VERIFICATION_STATUS_TRANSITIONS: dict[VerificationStatus, set[VerificationStatus]] = {
    VerificationStatus.NOT_STARTED: {VerificationStatus.PENDING},
    VerificationStatus.PENDING: {VerificationStatus.UNDER_REVIEW},
    VerificationStatus.UNDER_REVIEW: {
        VerificationStatus.APPROVED,
        VerificationStatus.REJECTED,
    },
    VerificationStatus.APPROVED: set(),
    VerificationStatus.REJECTED: set(),
    VerificationStatus.EXPIRED: set(),
}


class AsyncVerificationService:
    def __init__(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        provider: VerificationProvider | None = None,
    ) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.db.info["tenant_id"] = tenant_id
        self.repository = AsyncVerificationCaseRepository(db, tenant_id)
        self.audit_service = AsyncAuditService(db)
        self.provider = provider or get_verification_provider()
        self.workflow_validation_service = WorkflowValidationService(
            VERIFICATION_STATUS_TRANSITIONS
        )

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
            resource_type="verification_case",
            resource_id=case_id,
            user_id=self.db.info.get("tenant_user_id"),
            email=self.db.info.get("tenant_user_email"),
            ip_address=self.db.info.get("tenant_ip_address"),
            user_agent=self.db.info.get("tenant_user_agent"),
        )
        raise not_found("Verification case")

    async def _customer_audit(
        self,
        *,
        customer_id: UUID,
        user_id: UUID,
        case_id: UUID,
        action: str,
        old_value: object | None,
        new_value: object | None,
    ) -> None:
        self.db.add(
            CustomerAuditLog(
                tenant_id=self.tenant_id,
                customer_id=customer_id,
                user_id=user_id,
                resource_type="verification_case",
                resource_id=case_id,
                action=action,
                old_value=serialize_audit_value(old_value),
                new_value=serialize_audit_value(new_value),
            )
        )
        await self.db.flush()

    async def _record_verification_usage(self) -> None:
        await record_subscription_usage(self.db, self.tenant_id, "verification_checks")

    async def _notify_assignee(
        self,
        *,
        user_id: UUID,
        case: IdentityVerificationCase,
        status: VerificationStatus,
    ) -> None:
        await AsyncNotificationService(self.db, self.tenant_id).create_notification(
            user_id=user_id,
            title="Verification completed",
            message=f"Your verification case has been {status.value.lower()}.",
            event_type=NotificationEventType.VERIFICATION_COMPLETED,
            resource_type="verification_case",
            resource_id=case.id,
            channels=(NotificationChannel.IN_APP,),
        )

    async def _enqueue_webhook(
        self, event_type: str, *, case: IdentityVerificationCase, customer_id: UUID
    ) -> None:
        from app.webhooks.async_events import enqueue_webhook_event_async

        await enqueue_webhook_event_async(
            self.db,
            tenant_id=self.tenant_id,
            event_type=event_type,
            data={
                "verification_case_id": str(case.id),
                "customer_id": str(customer_id),
                "status": case.status.value,
            },
        )

    async def create_case(
        self,
        customer_id: UUID,
        case_data: VerificationCaseCreate,
        user_id: UUID,
        email: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> IdentityVerificationCase:
        await self._require_customer(customer_id)
        await self._record_verification_usage()
        case = await self.repository.create(
            IdentityVerificationCase(
                tenant_id=self.tenant_id,
                customer_id=customer_id,
                verification_type=case_data.verification_type,
                status=VerificationStatus.NOT_STARTED,
            )
        )
        await self.audit_service.log_event(
            event_type=AuditEventType.VERIFICATION_CASE_CREATED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="verification_case",
            resource_id=case.id,
        )
        await self._customer_audit(
            customer_id=customer_id,
            user_id=user_id,
            case_id=case.id,
            action="CREATE VERIFICATION CASE",
            old_value=None,
            new_value={
                "customer_id": str(customer_id),
                "verification_type": case.verification_type.value,
                "status": case.status.value,
            },
        )
        await self.db.commit()
        await self.db.refresh(case)
        return case

    async def get_cases_by_customer(
        self, customer_id: UUID
    ) -> list[IdentityVerificationCase]:
        await self._require_customer(customer_id)
        return await self.repository.get_by_customer_id(customer_id)

    async def update_status(
        self,
        customer_id: UUID,
        case_id: UUID,
        status_data: VerificationCaseStatusUpdate,
        user_id: UUID,
        email: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> IdentityVerificationCase:
        await self._require_customer(customer_id)
        case = await self.repository.get_by_id_and_customer(case_id, customer_id)
        if case is None:
            await self._deny_case(case_id)
        current_status = case.status
        new_status = status_data.status
        self.workflow_validation_service.validate_transition(
            current_status=current_status,
            new_status=new_status,
        )
        case.status = new_status
        if new_status in {VerificationStatus.APPROVED, VerificationStatus.REJECTED}:
            case.completed_at = utc_now()
            if case.assigned_to is not None:
                await self._notify_assignee(
                    user_id=case.assigned_to, case=case, status=new_status
                )
        case = await self.repository.update(case)
        if new_status == VerificationStatus.APPROVED:
            await self._enqueue_webhook(
                "verification.completed", case=case, customer_id=customer_id
            )
        elif new_status == VerificationStatus.REJECTED:
            await self._enqueue_webhook(
                "verification.failed", case=case, customer_id=customer_id
            )
        await self.audit_service.log_event(
            event_type=AuditEventType.VERIFICATION_CASE_STATUS_CHANGED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="verification_case",
            resource_id=case.id,
        )
        await self._customer_audit(
            customer_id=customer_id,
            user_id=user_id,
            case_id=case.id,
            action="UPDATE VERIFICATION STATUS",
            old_value={"status": current_status.value},
            new_value={"status": new_status.value},
        )
        await self.db.commit()
        await self.db.refresh(case)
        return case

    async def initiate_verification(
        self,
        customer_id: UUID,
        verification_data: VerificationCaseInitiation,
        user_id: UUID,
        email: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> IdentityVerificationCase:
        await self._require_customer(customer_id)
        existing = await self.repository.get_active_by_customer_and_type(
            customer_id, verification_data.verification_type
        )
        if existing is not None:
            raise bad_request(
                "An active verification case already exists for this customer."
            )
        case = IdentityVerificationCase(
            tenant_id=self.tenant_id,
            customer_id=customer_id,
            verification_type=verification_data.verification_type,
            status=VerificationStatus.PENDING,
        )
        try:
            case = await self.repository.create(case)
            await self.audit_service.log_event(
                event_type=AuditEventType.VERIFICATION_CASE_CREATED,
                user_id=user_id,
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
                resource_type="verification_case",
                resource_id=case.id,
            )
            await self._customer_audit(
                customer_id=customer_id,
                user_id=user_id,
                case_id=case.id,
                action="INITIATE VERIFICATION",
                old_value=None,
                new_value={
                    "customer_id": str(customer_id),
                    "verification_type": case.verification_type.value,
                    "status": case.status.value,
                },
            )
            await self.db.commit()
            await self.db.refresh(case)
        except IntegrityError as exc:
            await self.db.rollback()
            constraint_name = getattr(
                getattr(exc.orig, "diag", None), "constraint_name", None
            )
            if constraint_name == "uq_identity_verification_cases_active_customer_type":
                raise bad_request(
                    "An active verification case already exists for this customer."
                ) from exc
            raise
        return case

    async def submit_to_provider(
        self,
        *,
        user_id: UUID,
        email: str,
        customer_id: UUID,
        verification_case_id: UUID,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> VerificationResponse:
        await self._require_customer(customer_id)
        case = await self.repository.get_by_id_and_customer(
            verification_case_id, customer_id
        )
        if case is None:
            await self._deny_case(verification_case_id)
        provider_request = VerificationRequest(
            customer_id=customer_id,
            verification_case_id=case.id,
            verification_type=case.verification_type,
        )
        provider_response = await run_in_threadpool(
            self.provider.verify, provider_request
        )
        await self.audit_service.log_event(
            event_type=AuditEventType.VERIFICATION_PROVIDER_REQUEST,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="verification_case",
            resource_id=case.id,
        )
        await self.db.commit()
        return provider_response
