from uuid import UUID

from sqlalchemy.orm import Session

from app.models.investigation_note import InvestigationNote
from app.repositories.investigation_note_repository import (
    InvestigationNoteRepository,
)
from app.services.audit_service import AuditService
from app.utils.enums import (
    AuditEventType,
    InvestigationNoteType,
    UserRole,
)
from app.utils.errors import bad_request, forbidden, not_found


class InvestigationNoteService:
    def __init__(self, db: Session) -> None:
        self.db = db

        self.repository = InvestigationNoteRepository(db)
        self.audit_service = AuditService(db)

    def create_note(
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
        case = self.repository.get_case(
            customer_id=customer_id,
            case_id=case_id,
        )

        if case is None:
            raise not_found("Verification case")

        if case.assigned_to != user_id:
            raise forbidden(
                "Only the assigned reviewer can add investigation notes.",
            )

        normalized_note = note.strip()

        if not normalized_note:
            raise bad_request(
                "Investigation note cannot be empty.",
            )

        normalized_attachment = (
            attachment_reference.strip() if attachment_reference is not None else None
        )

        if normalized_attachment == "":
            normalized_attachment = None

        investigation_note = InvestigationNote(
            case_id=case.id,
            user_id=user_id,
            activity_type=activity_type,
            note=normalized_note,
            attachment_reference=normalized_attachment,
        )

        investigation_note = self.repository.create(
            investigation_note,
        )

        self.audit_service.log_event(
            user_id=user_id,
            email=user_email,
            event_type=(AuditEventType.INVESTIGATION_NOTE_CREATED),
            resource_type="investigation_note",
            resource_id=investigation_note.id,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        self.db.commit()

        return investigation_note

    def get_notes(
        self,
        *,
        customer_id: UUID,
        case_id: UUID,
        user_id: UUID,
        user_role: UserRole,
    ) -> list[InvestigationNote]:
        case = self.repository.get_case(
            customer_id=customer_id,
            case_id=case_id,
        )

        if case is None:
            raise not_found("Verification case")

        if user_role == UserRole.REVIEWER and case.assigned_to != user_id:
            raise forbidden(
                "You can only view investigation notes for cases assigned to you.",
            )

        return self.repository.get_by_case(case.id)
