"""Tenant-scoped asynchronous aggregate queries for verification reports."""

from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import CustomerDocument
from app.models.verification_case import IdentityVerificationCase
from app.utils.enums import DocumentStatus, VerificationStatus


class AsyncReportRepository:
    """Read verification and document summaries for exactly one tenant."""

    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        active_tenant_id = db.info.get("tenant_id")
        if active_tenant_id is not None and active_tenant_id != tenant_id:
            raise ValueError("Report repository tenant does not match session tenant.")
        db.info["tenant_id"] = tenant_id
        self.db = db
        self.tenant_id = tenant_id

    @staticmethod
    def _date_range(
        date_from: date | None,
        date_to: date | None,
    ) -> tuple[datetime | None, datetime | None]:
        start = (
            datetime.combine(date_from, time.min, tzinfo=timezone.utc)
            if date_from is not None
            else None
        )
        end = (
            datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=timezone.utc)
            if date_to is not None
            else None
        )
        return start, end

    async def get_verification_summary(
        self,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        status: VerificationStatus | None = None,
    ) -> dict[str, int]:
        start, end = self._date_range(date_from, date_to)
        statement = select(
            func.count(IdentityVerificationCase.id).label("total_cases"),
            func.count(
                case((IdentityVerificationCase.status == VerificationStatus.PENDING, 1))
            ).label("pending_cases"),
            func.count(
                case(
                    (IdentityVerificationCase.status == VerificationStatus.APPROVED, 1)
                )
            ).label("approved_cases"),
            func.count(
                case(
                    (IdentityVerificationCase.status == VerificationStatus.REJECTED, 1)
                )
            ).label("rejected_cases"),
        ).where(IdentityVerificationCase.tenant_id == self.tenant_id)

        if start is not None:
            statement = statement.where(IdentityVerificationCase.created_at >= start)
        if end is not None:
            statement = statement.where(IdentityVerificationCase.created_at < end)
        if status is not None:
            statement = statement.where(IdentityVerificationCase.status == status)

        row = (await self.db.execute(statement)).one()
        values = row._mapping
        return {
            "total_cases": int(values["total_cases"] or 0),
            "pending_cases": int(values["pending_cases"] or 0),
            "approved_cases": int(values["approved_cases"] or 0),
            "rejected_cases": int(values["rejected_cases"] or 0),
        }

    async def get_document_summary(
        self,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        status: DocumentStatus | None = None,
    ) -> dict[str, int]:
        start, end = self._date_range(date_from, date_to)
        statement = select(
            func.count(CustomerDocument.id).label("uploaded_documents"),
            func.count(
                case((CustomerDocument.status == DocumentStatus.VERIFIED, 1))
            ).label("accepted_documents"),
            func.count(
                case((CustomerDocument.status == DocumentStatus.REJECTED, 1))
            ).label("rejected_documents"),
        ).where(CustomerDocument.tenant_id == self.tenant_id)

        if start is not None:
            statement = statement.where(CustomerDocument.created_at >= start)
        if end is not None:
            statement = statement.where(CustomerDocument.created_at < end)
        if status is not None:
            statement = statement.where(CustomerDocument.status == status)

        row = (await self.db.execute(statement)).one()
        values = row._mapping
        return {
            "uploaded_documents": int(values["uploaded_documents"] or 0),
            "accepted_documents": int(values["accepted_documents"] or 0),
            "rejected_documents": int(values["rejected_documents"] or 0),
        }
