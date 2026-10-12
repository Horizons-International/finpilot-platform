from uuid import UUID

from sqlalchemy.orm import Session

from app.models.document_extraction import DocumentExtraction
from app.models.document_extraction_review_log import DocumentExtractionReviewLog
from app.models.user import User
from app.repositories.tenant_scoped_repository import TenantScopedRepository


class DocumentExtractionReviewLogRepository(
    TenantScopedRepository[DocumentExtractionReviewLog]
):
    def __init__(self, db: Session, tenant_id: UUID | None = None) -> None:
        resolved_tenant_id = (
            tenant_id if tenant_id is not None else db.info.get("tenant_id")
        )
        if not isinstance(resolved_tenant_id, UUID):
            raise ValueError("A tenant context is required for extraction review logs.")
        super().__init__(
            db=db,
            model=DocumentExtractionReviewLog,
            tenant_id=resolved_tenant_id,
        )

    def _validate_relationships(self, log: DocumentExtractionReviewLog) -> None:
        extraction_exists = (
            self.db.query(DocumentExtraction.id)
            .filter(
                DocumentExtraction.id == log.document_extraction_id,
                DocumentExtraction.tenant_id == self.tenant_id,
            )
            .first()
        )
        if extraction_exists is None:
            raise ValueError(
                "The document extraction does not belong to the current tenant."
            )

        reviewer_exists = (
            self.db.query(User.id)
            .filter(User.id == log.reviewer_id, User.tenant_id == self.tenant_id)
            .first()
        )
        if reviewer_exists is None:
            raise ValueError("The reviewer does not belong to the current tenant.")

    def create(self, log: DocumentExtractionReviewLog) -> DocumentExtractionReviewLog:
        self._validate_relationships(log)
        return super().create(log)

    def update(self, log: DocumentExtractionReviewLog) -> DocumentExtractionReviewLog:
        self._validate_relationships(log)
        return super().update(log)

    def get_by_extraction(
        self, extraction_id: UUID
    ) -> list[DocumentExtractionReviewLog]:
        return (
            self.query()
            .filter(DocumentExtractionReviewLog.document_extraction_id == extraction_id)
            .order_by(DocumentExtractionReviewLog.created_at.asc())
            .all()
        )
