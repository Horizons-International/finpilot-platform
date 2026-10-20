"""Tenant-aware persistence helpers for compliance document records."""

from uuid import UUID

from sqlalchemy.orm import Session

from app.models.compliance_document import (
    ComplianceDocument,
    ComplianceDocumentApproval,
    ComplianceDocumentVersion,
    ComplianceEvidenceRecord,
)
from app.repositories.tenant_scoped_repository import TenantScopedRepository


class ComplianceDocumentRepository(TenantScopedRepository[ComplianceDocument]):
    def __init__(self, db: Session, tenant_id: UUID) -> None:
        super().__init__(db=db, model=ComplianceDocument, tenant_id=tenant_id)

    def list_documents(
        self,
        *,
        category: str | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ComplianceDocument]:
        query = self.query()
        if category:
            query = query.filter(ComplianceDocument.category == category)
        if status:
            query = query.filter(ComplianceDocument.status == status)
        return (
            query.order_by(ComplianceDocument.updated_at.desc(), ComplianceDocument.id)
            .offset(offset)
            .limit(limit)
            .all()
        )

    def get_version(
        self, document_id: UUID, version: int
    ) -> ComplianceDocumentVersion | None:
        return (
            self.db.query(ComplianceDocumentVersion)
            .filter(
                ComplianceDocumentVersion.tenant_id == self.tenant_id,
                ComplianceDocumentVersion.document_id == document_id,
                ComplianceDocumentVersion.version == version,
            )
            .first()
        )

    def list_versions(self, document_id: UUID) -> list[ComplianceDocumentVersion]:
        return (
            self.db.query(ComplianceDocumentVersion)
            .filter(
                ComplianceDocumentVersion.tenant_id == self.tenant_id,
                ComplianceDocumentVersion.document_id == document_id,
            )
            .order_by(ComplianceDocumentVersion.version.desc())
            .all()
        )

    def list_approvals(self, document_id: UUID) -> list[ComplianceDocumentApproval]:
        return (
            self.db.query(ComplianceDocumentApproval)
            .filter(
                ComplianceDocumentApproval.tenant_id == self.tenant_id,
                ComplianceDocumentApproval.document_id == document_id,
            )
            .order_by(ComplianceDocumentApproval.created_at.desc())
            .all()
        )

    def pending_approval(self, document_id: UUID) -> ComplianceDocumentApproval | None:
        from app.models.compliance_document import ComplianceApprovalStatus

        return (
            self.db.query(ComplianceDocumentApproval)
            .filter(
                ComplianceDocumentApproval.tenant_id == self.tenant_id,
                ComplianceDocumentApproval.document_id == document_id,
                ComplianceDocumentApproval.status == ComplianceApprovalStatus.PENDING,
            )
            .order_by(ComplianceDocumentApproval.created_at.desc())
            .first()
        )

    def list_evidence(self, document_id: UUID) -> list[ComplianceEvidenceRecord]:
        return (
            self.db.query(ComplianceEvidenceRecord)
            .filter(
                ComplianceEvidenceRecord.tenant_id == self.tenant_id,
                ComplianceEvidenceRecord.document_id == document_id,
            )
            .order_by(ComplianceEvidenceRecord.collected_at.desc())
            .all()
        )
