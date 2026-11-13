"""Native-async verification assignments, reviews and document-type administration."""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.customer_audit_log import CustomerAuditLog
from app.models.user import User
from app.models.verification_case import IdentityVerificationCase
from app.models.verification_case_assignment_history import (
    VerificationCaseAssignmentHistory,
)
from app.models.verification_document_type import VerificationDocumentType
from app.models.verification_review import VerificationReview
from app.schemas.verification_document_type import (
    VerificationDocumentTypeCreate,
    VerificationDocumentTypeUpdate,
)
from app.services.async_audit_service import AsyncAuditService
from app.services.async_notification_service import AsyncNotificationService
from app.utils.enums import (
    AuditEventType,
    NotificationChannel,
    NotificationEventType,
    ReviewDecision,
    UserRole,
    UserStatus,
    VerificationStatus,
)
from app.utils.errors import bad_request, not_found


class _AsyncVerificationService:
    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        active = db.info.get("tenant_id")
        if active is not None and active != tenant_id:
            raise ValueError(
                "Verification service tenant does not match session tenant."
            )
        db.info["tenant_id"] = tenant_id
        self.db = db
        self.tenant_id = tenant_id
        self.audit = AsyncAuditService(db)

    async def _require_case(
        self, customer_id: UUID, verification_case_id: UUID, *, for_update: bool = False
    ) -> IdentityVerificationCase:
        statement = (
            select(IdentityVerificationCase)
            .join(Customer, Customer.id == IdentityVerificationCase.customer_id)
            .where(
                IdentityVerificationCase.id == verification_case_id,
                IdentityVerificationCase.customer_id == customer_id,
                IdentityVerificationCase.tenant_id == self.tenant_id,
                Customer.tenant_id == self.tenant_id,
            )
        )
        if for_update:
            statement = statement.with_for_update()
        case = await self.db.scalar(statement)
        if case is None:
            await self.audit.log_access_denied(
                resource_type="verification_case",
                resource_id=verification_case_id,
                user_id=self.db.info.get("tenant_user_id"),
                email=self.db.info.get("tenant_user_email"),
                ip_address=self.db.info.get("tenant_ip_address"),
                user_agent=self.db.info.get("tenant_user_agent"),
            )
            raise not_found("Verification case")
        return case

    async def _customer_audit(
        self,
        *,
        customer_id: UUID,
        actor_id: UUID,
        resource_id: UUID,
        action: str,
        old_value: dict | None,
        new_value: dict | None,
    ) -> None:
        self.db.add(
            CustomerAuditLog(
                tenant_id=self.tenant_id,
                customer_id=customer_id,
                user_id=actor_id,
                resource_type="verification_case",
                resource_id=resource_id,
                action=action,
                old_value=old_value,
                new_value=new_value,
            )
        )
        await self.db.flush()


class AsyncVerificationCaseAssignmentService(_AsyncVerificationService):
    async def assign_case(
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
        case = await self._require_case(
            customer_id, verification_case_id, for_update=True
        )
        reviewer = await self.db.scalar(
            select(User).where(
                User.id == reviewer_id,
                User.tenant_id == self.tenant_id,
                User.is_platform_admin.is_(False),
                User.is_deleted.is_(False),
            )
        )
        if reviewer is None:
            await self.audit.log_access_denied(
                resource_type="user",
                resource_id=reviewer_id,
                user_id=assigned_by,
                email=assigned_by_email,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            raise not_found("Reviewer")
        if reviewer.role != UserRole.REVIEWER:
            raise bad_request("The selected user is not a reviewer.")
        if reviewer.status != UserStatus.ACTIVE:
            raise bad_request("The selected reviewer is not active.")
        if reviewer.is_deleted:
            raise bad_request("The selected reviewer has been deleted.")
        previous = case.assigned_to
        if previous == reviewer_id:
            raise bad_request(
                "The verification case is already assigned to this reviewer."
            )
        assigned_at = datetime.now(timezone.utc)
        case.assigned_to = reviewer_id
        case.assigned_at = assigned_at
        case.assigned_by = assigned_by
        history = VerificationCaseAssignmentHistory(
            tenant_id=self.tenant_id,
            verification_case_id=case.id,
            assigned_to=reviewer_id,
            previous_reviewer=previous,
            assigned_by=assigned_by,
            assigned_at=assigned_at,
        )
        self.db.add(history)
        await self.audit.log_event(
            event_type=AuditEventType.VERIFICATION_CASE_ASSIGNED,
            user_id=assigned_by,
            email=assigned_by_email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="verification_case",
            resource_id=case.id,
        )
        await AsyncNotificationService(self.db, self.tenant_id).create_notification(
            user_id=reviewer_id,
            title="Verification case assigned",
            message=f"Verification case {case.id} has been assigned.",
            event_type=NotificationEventType.VERIFICATION_CASE_ASSIGNED,
            resource_type="verification_case",
            resource_id=case.id,
            channels=(NotificationChannel.IN_APP,),
        )
        await self.db.commit()
        await self.db.refresh(history)
        return history

    async def get_assignment_history(
        self, *, customer_id: UUID, verification_case_id: UUID
    ) -> list[VerificationCaseAssignmentHistory]:
        await self._require_case(customer_id, verification_case_id)
        result = await self.db.scalars(
            select(VerificationCaseAssignmentHistory)
            .where(
                VerificationCaseAssignmentHistory.tenant_id == self.tenant_id,
                VerificationCaseAssignmentHistory.verification_case_id
                == verification_case_id,
            )
            .order_by(VerificationCaseAssignmentHistory.assigned_at.desc())
        )
        return list(result.all())

    async def get_assigned_cases(
        self, reviewer_id: UUID
    ) -> list[IdentityVerificationCase]:
        result = await self.db.scalars(
            select(IdentityVerificationCase)
            .where(
                IdentityVerificationCase.tenant_id == self.tenant_id,
                IdentityVerificationCase.assigned_to == reviewer_id,
            )
            .order_by(
                IdentityVerificationCase.assigned_at.desc().nullslast(),
                IdentityVerificationCase.created_at.desc(),
            )
        )
        return list(result.all())

    async def get_all_assigned_cases(self) -> list[IdentityVerificationCase]:
        result = await self.db.scalars(
            select(IdentityVerificationCase)
            .where(
                IdentityVerificationCase.tenant_id == self.tenant_id,
                IdentityVerificationCase.assigned_to.is_not(None),
            )
            .order_by(
                IdentityVerificationCase.assigned_at.desc().nullslast(),
                IdentityVerificationCase.created_at.desc(),
            )
        )
        return list(result.all())


class AsyncVerificationReviewService(_AsyncVerificationService):
    async def _get_assigned_case(
        self, customer_id: UUID, verification_case_id: UUID, reviewer_id: UUID
    ) -> IdentityVerificationCase:
        case = await self._require_case(
            customer_id, verification_case_id, for_update=True
        )
        if case.assigned_to != reviewer_id:
            await self.audit.log_access_denied(
                resource_type="verification_case",
                resource_id=verification_case_id,
                user_id=reviewer_id,
                email=self.db.info.get("tenant_user_email"),
                ip_address=self.db.info.get("tenant_ip_address"),
                user_agent=self.db.info.get("tenant_user_agent"),
            )
            raise not_found("Verification case")
        return case

    async def start_review(
        self,
        *,
        customer_id: UUID,
        verification_case_id: UUID,
        reviewer_id: UUID,
        email: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        case = await self._get_assigned_case(
            customer_id, verification_case_id, reviewer_id
        )
        if case.status != VerificationStatus.PENDING:
            raise bad_request(
                "Verification case cannot be started for review in its current status."
            )
        old_status = case.status
        case.status = VerificationStatus.UNDER_REVIEW
        await self.audit.log_event(
            event_type=AuditEventType.VERIFICATION_CASE_STATUS_CHANGED,
            user_id=reviewer_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="verification_case",
            resource_id=verification_case_id,
        )
        await self._customer_audit(
            customer_id=customer_id,
            actor_id=reviewer_id,
            resource_id=verification_case_id,
            action="START VERIFICATION REVIEW",
            old_value={"status": old_status.value},
            new_value={"status": case.status.value},
        )
        await self.db.commit()

    async def create_review(
        self,
        *,
        customer_id: UUID,
        verification_case_id: UUID,
        reviewer_id: UUID,
        email: str,
        decision: ReviewDecision,
        notes: str | None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> VerificationReview:
        case = await self._get_assigned_case(
            customer_id, verification_case_id, reviewer_id
        )
        if case.status != VerificationStatus.UNDER_REVIEW:
            raise bad_request(
                "Verification case must be under review before a decision can be made."
            )
        statuses = {
            ReviewDecision.APPROVE: VerificationStatus.APPROVED,
            ReviewDecision.REJECT: VerificationStatus.REJECTED,
            ReviewDecision.REQUEST_MORE_INFORMATION: VerificationStatus.PENDING,
        }
        if decision not in statuses:
            raise bad_request("Invalid review decision.")
        old_status = case.status
        new_status = statuses[decision]
        review = VerificationReview(
            tenant_id=self.tenant_id,
            verification_case_id=verification_case_id,
            reviewer_id=reviewer_id,
            decision=decision,
            notes=notes,
        )
        self.db.add(review)
        case.status = new_status
        if new_status in {VerificationStatus.APPROVED, VerificationStatus.REJECTED}:
            from app.utils.date_time import utc_now

            case.completed_at = utc_now()
        await self.audit.log_event(
            event_type=AuditEventType.VERIFICATION_CASE_STATUS_CHANGED,
            user_id=reviewer_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="verification_case",
            resource_id=verification_case_id,
        )
        await self._customer_audit(
            customer_id=customer_id,
            actor_id=reviewer_id,
            resource_id=verification_case_id,
            action="REVIEW VERIFICATION CASE",
            old_value={"status": old_status.value},
            new_value={
                "status": new_status.value,
                "decision": decision.value,
                "notes": notes,
            },
        )
        await AsyncNotificationService(self.db, self.tenant_id).create_notification(
            user_id=reviewer_id,
            title="Verification completed",
            message=f"Your verification case has been {new_status.value.lower()}.",
            event_type=NotificationEventType.VERIFICATION_COMPLETED,
            resource_type="verification_case",
            resource_id=case.id,
            channels=(NotificationChannel.IN_APP,),
        )
        await self.db.commit()
        await self.db.refresh(review)
        return review


class AsyncVerificationDocumentTypeService:
    """Async management for global verification document type definitions."""

    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        active = db.info.get("tenant_id")
        if active is not None and active != tenant_id:
            raise ValueError(
                "Document type service tenant does not match session tenant."
            )
        db.info["tenant_id"] = tenant_id
        self.db = db
        self.audit = AsyncAuditService(db)

    async def get_all(self) -> list[VerificationDocumentType]:
        result = await self.db.scalars(
            select(VerificationDocumentType).order_by(
                VerificationDocumentType.name.asc()
            )
        )
        return list(result.all())

    async def get_active(self) -> list[VerificationDocumentType]:
        result = await self.db.scalars(
            select(VerificationDocumentType)
            .where(VerificationDocumentType.is_active.is_(True))
            .order_by(VerificationDocumentType.name.asc())
        )
        return list(result.all())

    async def get_by_id(self, document_type_id: UUID) -> VerificationDocumentType:
        item = await self.db.get(VerificationDocumentType, document_type_id)
        if item is None:
            raise not_found("Verification document type")
        return item

    async def create(
        self,
        data: VerificationDocumentTypeCreate,
        user_id: UUID,
        email: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> VerificationDocumentType:
        existing = await self.db.scalar(
            select(VerificationDocumentType).where(
                VerificationDocumentType.name == data.name
            )
        )
        if existing is not None:
            raise bad_request(
                "A verification document type with this name already exists."
            )
        item = VerificationDocumentType(
            name=data.name,
            category=data.category,
            supported_countries=data.supported_countries,
            is_active=data.is_active,
        )
        self.db.add(item)
        try:
            await self.db.flush()
            await self.audit.log_event(
                event_type=AuditEventType.VERIFICATION_DOCUMENT_TYPE_CREATED,
                user_id=user_id,
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
                resource_type="verification_document_type",
                resource_id=item.id,
            )
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            raise bad_request(
                "A verification document type with this name already exists."
            ) from exc
        await self.db.refresh(item)
        return item

    async def update(
        self,
        document_type_id: UUID,
        data: VerificationDocumentTypeUpdate,
        user_id: UUID,
        email: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> VerificationDocumentType:
        item = await self.get_by_id(document_type_id)
        changes = data.model_dump(exclude_unset=True)
        if "name" in changes and changes["name"] != item.name:
            duplicate = await self.db.scalar(
                select(VerificationDocumentType.id).where(
                    VerificationDocumentType.name == changes["name"],
                    VerificationDocumentType.id != item.id,
                )
            )
            if duplicate is not None:
                raise bad_request(
                    "A verification document type with this name already exists."
                )
        status_changed = (
            "is_active" in changes and changes["is_active"] != item.is_active
        )
        for field, value in changes.items():
            setattr(item, field, value)
        try:
            await self.db.flush()
            await self.audit.log_event(
                event_type=(
                    AuditEventType.VERIFICATION_DOCUMENT_TYPE_STATUS_CHANGED
                    if status_changed
                    else AuditEventType.VERIFICATION_DOCUMENT_TYPE_UPDATED
                ),
                user_id=user_id,
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
                resource_type="verification_document_type",
                resource_id=item.id,
            )
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            raise bad_request(
                "A verification document type with this name already exists."
            ) from exc
        await self.db.refresh(item)
        return item
