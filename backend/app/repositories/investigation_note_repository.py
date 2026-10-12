from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.investigation_note import InvestigationNote
from app.models.user import User
from app.models.verification_case import IdentityVerificationCase
from app.repositories.tenant_scoped_repository import TenantScopedRepository


class InvestigationNoteRepository(TenantScopedRepository[InvestigationNote]):
    def __init__(self, db: Session, tenant_id: UUID | None = None) -> None:
        resolved_tenant_id = (
            tenant_id if tenant_id is not None else db.info.get("tenant_id")
        )
        if not isinstance(resolved_tenant_id, UUID):
            raise ValueError("A tenant context is required for investigation notes.")
        super().__init__(db=db, model=InvestigationNote, tenant_id=resolved_tenant_id)

    def get_case(
        self,
        *,
        customer_id: UUID,
        case_id: UUID,
    ) -> IdentityVerificationCase | None:
        statement = select(IdentityVerificationCase).where(
            IdentityVerificationCase.id == case_id,
            IdentityVerificationCase.customer_id == customer_id,
            IdentityVerificationCase.tenant_id == self.tenant_id,
        )
        return self.db.scalar(statement)

    def _validate_relationships(self, note: InvestigationNote) -> None:
        case_exists = (
            self.db.query(IdentityVerificationCase.id)
            .filter(
                IdentityVerificationCase.id == note.case_id,
                IdentityVerificationCase.tenant_id == self.tenant_id,
            )
            .first()
        )
        if case_exists is None:
            raise ValueError(
                "The verification case does not belong to the current tenant."
            )

        user_exists = (
            self.db.query(User.id)
            .filter(User.id == note.user_id, User.tenant_id == self.tenant_id)
            .first()
        )
        if user_exists is None:
            raise ValueError("The note author does not belong to the current tenant.")

    def create(self, investigation_note: InvestigationNote) -> InvestigationNote:
        self._validate_relationships(investigation_note)
        return super().create(investigation_note)

    def update(self, investigation_note: InvestigationNote) -> InvestigationNote:
        self._validate_relationships(investigation_note)
        return super().update(investigation_note)

    def get_by_case(self, case_id: UUID) -> list[InvestigationNote]:
        return (
            self.query()
            .filter(InvestigationNote.case_id == case_id)
            .order_by(InvestigationNote.created_at.desc())
            .all()
        )
