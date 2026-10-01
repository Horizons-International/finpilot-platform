from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.rag.embeddings import EmbeddingService
from app.rag.retrieval import RetrievalService
from app.services.ai_compliance_service import (
    AIComplianceService,
)
from app.services.ai_usage_service import AIUsageService
from app.services.compliance_service import ComplianceService
from app.services.customer_onboarding import (
    CustomerOnboardingService,
)
from app.services.document_review_service import DocumentReviewService
from app.services.document_service import DocumentService
from app.services.file_service import FileService
from app.services.knowledge_document_service import (
    KnowledgeDocumentService,
)
from app.services.knowledge_indexing_service import KnowledgeIndexingService
from app.services.risk_scoring_service import RiskScoringService
from app.services.verification_review_service import VerificationReviewService
from app.services.verification_service import VerificationService
from app.services.workflow_service import WorkflowService
from app.storages.base_storage import BaseStorage
from app.storages.local_storage import LocalStorage


def get_storage() -> BaseStorage:
    return LocalStorage(settings.STORAGE_PATH)


def get_file_service(
    db: Session = Depends(get_db),
    storage: BaseStorage = Depends(get_storage),
) -> FileService:
    return FileService(
        db=db,
        storage=storage,
    )


def get_document_service(
    db: Session = Depends(get_db),
    storage: BaseStorage = Depends(get_storage),
) -> DocumentService:
    return DocumentService(
        db=db,
        storage=storage,
    )


def get_verification_service(
    db: Session = Depends(get_db),
) -> VerificationService:
    return VerificationService(db)


def get_verification_review_service(
    db: Session = Depends(get_db),
) -> VerificationReviewService:
    return VerificationReviewService(db)


def get_knowledge_document_service(
    db: Session = Depends(get_db),
    file_service: FileService = Depends(get_file_service),
) -> KnowledgeDocumentService:
    return KnowledgeDocumentService(
        db=db,
        file_service=file_service,
    )


def get_knowledge_indexing_service(
    db: Session = Depends(get_db),
    file_service: FileService = Depends(get_file_service),
) -> KnowledgeIndexingService:
    return KnowledgeIndexingService(
        db=db,
        file_service=file_service,
        embedding_service=EmbeddingService(),
    )


def get_retrieval_service(
    db: Session = Depends(get_db),
) -> RetrievalService:
    return RetrievalService(db)


def get_ai_usage_service(
    db: Session = Depends(get_db),
) -> AIUsageService:
    return AIUsageService(db)


def get_compliance_service(
    db: Session = Depends(get_db),
) -> ComplianceService:
    return ComplianceService(db)


def get_document_review_service(
    db: Session = Depends(get_db),
) -> DocumentReviewService:
    return DocumentReviewService(db)


def get_ai_compliance_service(
    db: Session = Depends(get_db),
    retrieval_service: RetrievalService = Depends(
        get_retrieval_service,
    ),
) -> AIComplianceService:
    return AIComplianceService(
        db,
        retrieval_service=retrieval_service,
    )


def get_risk_scoring_service(
    db: Session = Depends(get_db),
) -> RiskScoringService:
    return RiskScoringService(db)


def get_workflow_service(
    db: Session = Depends(get_db),
) -> WorkflowService:
    return WorkflowService(db)


def get_customer_onboarding_service(
    db: Session = Depends(get_db),
    workflow_service: WorkflowService = Depends(
        get_workflow_service,
    ),
) -> CustomerOnboardingService:
    return CustomerOnboardingService(
        db=db,
        workflow_service=workflow_service,
    )
