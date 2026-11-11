"""Async tenant-aware persistence helpers for compliance document records."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.compliance_document import (
    ComplianceApprovalStatus,
    ComplianceDocument,
    ComplianceDocumentApproval,
    ComplianceDocumentVersion,
    ComplianceEvidenceRecord,
)
from app.repositories.async_tenant_scoped_repository import (
    AsyncTenantScopedRepository,
)


class AsyncComplianceDocumentRepository(
    AsyncTenantScopedRepository[ComplianceDocument]
):
    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        super().__init__(db=db, model=ComplianceDocument, tenant_id=tenant_id)

    async def list_documents(
        self,
        *,
        category: str | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ComplianceDocument]:
        statement = self.query()
        if category:
            statement = statement.where(ComplianceDocument.category == category)
        if status:
            statement = statement.where(ComplianceDocument.status == status)
        statement = (
            statement.order_by(
                ComplianceDocument.updated_at.desc(),
                ComplianceDocument.id,
            )
            .offset(offset)
            .limit(limit)
        )
        result = await self.db.scalars(statement)
        return list(result.all())

    async def get_version(
        self,
        document_id: UUID,
        version: int,
    ) -> ComplianceDocumentVersion | None:
        statement = select(ComplianceDocumentVersion).where(
            ComplianceDocumentVersion.tenant_id == self.tenant_id,
            ComplianceDocumentVersion.document_id == document_id,
            ComplianceDocumentVersion.version == version,
        )
        return await self.db.scalar(statement)

    async def list_versions(self, document_id: UUID) -> list[ComplianceDocumentVersion]:
        statement = (
            select(ComplianceDocumentVersion)
            .where(
                ComplianceDocumentVersion.tenant_id == self.tenant_id,
                ComplianceDocumentVersion.document_id == document_id,
            )
            .order_by(ComplianceDocumentVersion.version.desc())
        )
        result = await self.db.scalars(statement)
        return list(result.all())

    async def list_approvals(
        self,
        document_id: UUID,
    ) -> list[ComplianceDocumentApproval]:
        statement = (
            select(ComplianceDocumentApproval)
            .where(
                ComplianceDocumentApproval.tenant_id == self.tenant_id,
                ComplianceDocumentApproval.document_id == document_id,
            )
            .order_by(ComplianceDocumentApproval.created_at.desc())
        )
        result = await self.db.scalars(statement)
        return list(result.all())

    async def pending_approval(
        self,
        document_id: UUID,
    ) -> ComplianceDocumentApproval | None:
        statement = (
            select(ComplianceDocumentApproval)
            .where(
                ComplianceDocumentApproval.tenant_id == self.tenant_id,
                ComplianceDocumentApproval.document_id == document_id,
                ComplianceDocumentApproval.status == ComplianceApprovalStatus.PENDING,
            )
            .order_by(ComplianceDocumentApproval.created_at.desc())
        )
        return await self.db.scalar(statement)

    async def list_evidence(
        self,
        document_id: UUID,
    ) -> list[ComplianceEvidenceRecord]:
        statement = (
            select(ComplianceEvidenceRecord)
            .where(
                ComplianceEvidenceRecord.tenant_id == self.tenant_id,
                ComplianceEvidenceRecord.document_id == document_id,
            )
            .order_by(ComplianceEvidenceRecord.collected_at.desc())
        )
        result = await self.db.scalars(statement)
        return list(result.all())
