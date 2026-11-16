from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.investigation_note import InvestigationNote
from app.models.user import User
from app.models.verification_case import IdentityVerificationCase


class AsyncInvestigationNoteRepository:
    """Tenant-scoped async persistence for verification investigation notes."""

    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        self.db = db
        self.tenant_id = tenant_id
        session_tenant_id = db.info.get("tenant_id")
        if session_tenant_id is not None and session_tenant_id != tenant_id:
            raise ValueError("The session is already bound to another tenant.")
        db.info["tenant_id"] = tenant_id

    async def get_case(
        self, *, customer_id: UUID, case_id: UUID
    ) -> IdentityVerificationCase | None:
        return await self.db.scalar(
            select(IdentityVerificationCase).where(
                IdentityVerificationCase.id == case_id,
                IdentityVerificationCase.customer_id == customer_id,
                IdentityVerificationCase.tenant_id == self.tenant_id,
            )
        )

    async def create(self, note: InvestigationNote) -> InvestigationNote:
        case_exists = await self.db.scalar(
            select(IdentityVerificationCase.id).where(
                IdentityVerificationCase.id == note.case_id,
                IdentityVerificationCase.tenant_id == self.tenant_id,
            )
        )
        if case_exists is None:
            raise ValueError("The verification case does not belong to this tenant.")

        user_exists = await self.db.scalar(
            select(User.id).where(
                User.id == note.user_id,
                User.tenant_id == self.tenant_id,
            )
        )
        if user_exists is None:
            raise ValueError("The note author does not belong to this tenant.")

        self.db.add(note)
        await self.db.flush()
        return note

    async def get_by_case(self, case_id: UUID) -> list[InvestigationNote]:
        result = await self.db.scalars(
            select(InvestigationNote)
            .where(
                InvestigationNote.case_id == case_id,
                InvestigationNote.tenant_id == self.tenant_id,
            )
            .order_by(
                InvestigationNote.created_at.desc(),
                InvestigationNote.id.desc(),
            )
        )
        return list(result.all())
