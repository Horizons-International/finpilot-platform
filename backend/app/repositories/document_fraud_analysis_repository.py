"""Tenant-scoped data access for document fraud analysis."""

from uuid import UUID

from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.document import CustomerDocument
from app.models.document_extraction import DocumentExtraction
from app.models.document_fraud_analysis import DocumentFraudAnalysis
from app.models.ocr_result import OCRResult
from app.models.verification_document_type import VerificationDocumentType
from app.repositories.tenant_scoped_repository import TenantScopedRepository
from app.utils.enums import ExtractionStatus, OCRProcessingStatus


class DocumentFraudAnalysisRepository(TenantScopedRepository[DocumentFraudAnalysis]):
    """Database operations for one tenant's document fraud analyses."""

    def __init__(self, db: Session, tenant_id: UUID) -> None:
        super().__init__(
            db=db,
            model=DocumentFraudAnalysis,
            tenant_id=tenant_id,
        )

    def get_document(
        self,
        document_id: UUID,
    ) -> CustomerDocument | None:
        return (
            self.db.query(CustomerDocument)
            .filter(
                CustomerDocument.id == document_id,
                CustomerDocument.tenant_id == self.tenant_id,
            )
            .first()
        )

    def get_customer(self, customer_id: UUID) -> Customer | None:
        return (
            self.db.query(Customer)
            .filter(
                Customer.id == customer_id,
                Customer.tenant_id == self.tenant_id,
            )
            .first()
        )

    def get_document_type(
        self,
        document_type_id: UUID,
    ) -> VerificationDocumentType | None:
        return (
            self.db.query(VerificationDocumentType)
            .filter(VerificationDocumentType.id == document_type_id)
            .first()
        )

    def get_latest_extraction(
        self,
        document_id: UUID,
    ) -> DocumentExtraction | None:
        return (
            self.db.query(DocumentExtraction)
            .filter(
                DocumentExtraction.tenant_id == self.tenant_id,
                DocumentExtraction.document_id == document_id,
                DocumentExtraction.status == ExtractionStatus.COMPLETED,
            )
            .order_by(DocumentExtraction.created_at.desc())
            .first()
        )

    def get_latest_ocr(
        self,
        document_id: UUID,
    ) -> OCRResult | None:
        return (
            self.db.query(OCRResult)
            .filter(
                OCRResult.tenant_id == self.tenant_id,
                OCRResult.document_id == document_id,
                OCRResult.status == OCRProcessingStatus.COMPLETED,
            )
            .order_by(OCRResult.created_at.desc())
            .first()
        )

    def get_document_number_candidates(
        self,
        excluded_document_id: UUID,
    ) -> list[tuple[DocumentExtraction, CustomerDocument]]:
        rows = (
            self.db.query(DocumentExtraction, CustomerDocument)
            .join(
                CustomerDocument,
                and_(
                    CustomerDocument.id == DocumentExtraction.document_id,
                    CustomerDocument.tenant_id == DocumentExtraction.tenant_id,
                ),
            )
            .filter(
                DocumentExtraction.tenant_id == self.tenant_id,
                CustomerDocument.tenant_id == self.tenant_id,
                DocumentExtraction.document_id != excluded_document_id,
                DocumentExtraction.status == ExtractionStatus.COMPLETED,
                DocumentExtraction.document_number.is_not(None),
            )
            .order_by(DocumentExtraction.created_at.desc())
            .limit(500)
            .all()
        )

        return [(row[0], row[1]) for row in rows]

    def get_ocr_duplicate_candidates(
        self,
        excluded_document_id: UUID,
    ) -> list[tuple[OCRResult, CustomerDocument]]:
        rows = (
            self.db.query(OCRResult, CustomerDocument)
            .join(
                CustomerDocument,
                and_(
                    CustomerDocument.id == OCRResult.document_id,
                    CustomerDocument.tenant_id == OCRResult.tenant_id,
                ),
            )
            .filter(
                OCRResult.tenant_id == self.tenant_id,
                CustomerDocument.tenant_id == self.tenant_id,
                CustomerDocument.id != excluded_document_id,
                OCRResult.status == OCRProcessingStatus.COMPLETED,
                OCRResult.extracted_text.is_not(None),
            )
            .order_by(OCRResult.created_at.desc())
            .limit(500)
            .all()
        )

        return [(row[0], row[1]) for row in rows]

    def list_history(
        self,
        *,
        document_id: UUID | None = None,
        customer_id: UUID | None = None,
        limit: int = 50,
    ) -> tuple[list[DocumentFraudAnalysis], int]:
        query = self.query()

        if document_id is not None:
            query = query.filter(DocumentFraudAnalysis.document_id == document_id)

        if customer_id is not None:
            query = query.filter(DocumentFraudAnalysis.customer_id == customer_id)

        total = query.count()
        rows = (
            query.order_by(DocumentFraudAnalysis.created_at.desc()).limit(limit).all()
        )
        return rows, total

    def get_analysis(
        self,
        analysis_id: UUID,
    ) -> DocumentFraudAnalysis | None:
        return self.get_by_id(analysis_id)
