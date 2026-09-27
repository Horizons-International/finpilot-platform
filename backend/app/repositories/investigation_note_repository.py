from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.investigation_note import InvestigationNote
from app.models.verification_case import IdentityVerificationCase


class InvestigationNoteRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_case(
        self,
        *,
        customer_id: UUID,
        case_id: UUID,
    ) -> IdentityVerificationCase | None:
        statement = select(IdentityVerificationCase).where(
            IdentityVerificationCase.id == case_id,
            IdentityVerificationCase.customer_id == customer_id,
        )

        return self.db.scalar(statement)

    def create(
        self,
        investigation_note: InvestigationNote,
    ) -> InvestigationNote:
        self.db.add(investigation_note)
        self.db.flush()
        self.db.refresh(investigation_note)

        return investigation_note

    def get_by_case(
        self,
        case_id: UUID,
    ) -> list[InvestigationNote]:
        statement = (
            select(InvestigationNote)
            .where(
                InvestigationNote.case_id == case_id,
            )
            .order_by(
                InvestigationNote.created_at.desc(),
            )
        )

        return list(self.db.scalars(statement).all())
