from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.investigation_note import InvestigationNote
from app.repositories.async_investigation_note_repository import (
    AsyncInvestigationNoteRepository,
)
from app.services.async_audit_service import AsyncAuditService
from app.utils.enums import AuditEventType, InvestigationNoteType, UserRole
from app.utils.errors import bad_request, forbidden, not_found


class AsyncInvestigationNoteService:
    """Async investigation-note workflow; audit and note share one transaction."""

    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.repository = AsyncInvestigationNoteRepository(db, tenant_id)
        self.audit_service = AsyncAuditService(db)

    async def create_note(
        self,
        *,
        customer_id: UUID,
        case_id: UUID,
        user_id: UUID,
        user_email: str,
        activity_type: InvestigationNoteType,
        note: str,
        attachment_reference: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> InvestigationNote:
        case = await self.repository.get_case(customer_id=customer_id, case_id=case_id)
        if case is None:
            await self._deny_case_access(
                case_id, user_id, user_email, ip_address, user_agent
            )
            raise not_found("Verification case")
        if case.assigned_to != user_id:
            raise forbidden("Only the assigned reviewer can add investigation notes.")

        normalized_note = note.strip()
        if not normalized_note:
            raise bad_request("Investigation note cannot be empty.")
        normalized_attachment = (
            attachment_reference.strip() if attachment_reference is not None else None
        )
        if normalized_attachment == "":
            normalized_attachment = None

        item = InvestigationNote(
            tenant_id=self.tenant_id,
            case_id=case.id,
            user_id=user_id,
            activity_type=activity_type,
            note=normalized_note,
            attachment_reference=normalized_attachment,
        )
        await self.repository.create(item)
        await self.audit_service.log_event(
            user_id=user_id,
            email=user_email,
            event_type=AuditEventType.INVESTIGATION_NOTE_CREATED,
            resource_type="investigation_note",
            resource_id=item.id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def get_notes(
        self,
        *,
        customer_id: UUID,
        case_id: UUID,
        user_id: UUID,
        user_role: UserRole,
        user_email: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> list[InvestigationNote]:
        case = await self.repository.get_case(customer_id=customer_id, case_id=case_id)
        if case is None:
            await self._deny_case_access(
                case_id, user_id, user_email, ip_address, user_agent
            )
            raise not_found("Verification case")
        if user_role == UserRole.REVIEWER and case.assigned_to != user_id:
            raise forbidden(
                "You can only view investigation notes for cases assigned to you."
            )
        return await self.repository.get_by_case(case.id)

    async def _deny_case_access(
        self,
        case_id: UUID,
        user_id: UUID,
        email: str | None,
        ip_address: str | None,
        user_agent: str | None,
    ) -> None:
        # Preserve the existing anti-enumeration behavior and access-denied audit.
        await self.db.rollback()
        await self.audit_service.log_access_denied(
            resource_type="verification_case",
            resource_id=case_id,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
        )
