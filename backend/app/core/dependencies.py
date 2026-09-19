from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.user import User
from app.rag.embeddings import EmbeddingService
from app.rag.retrieval import RetrievalService
from app.services.ai_usage_service import AIUsageService
from app.services.compliance_service import ComplianceService
from app.services.document_service import DocumentService
from app.services.file_service import FileService
from app.services.knowledge_document_service import (
    KnowledgeDocumentService,
)
from app.services.knowledge_indexing_service import KnowledgeIndexingService
from app.services.verification_review_service import VerificationReviewService
from app.services.verification_service import VerificationService
from app.storages.base_storage import BaseStorage
from app.storages.local_storage import LocalStorage
from app.utils.enums import UserStatus
from app.utils.errors import unauthorized

security = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    token = credentials.credentials

    try:
        payload = decode_access_token(token)
    except JWTError:
        raise unauthorized("Invalid or expired token")

    if payload.get("type") != "access":
        raise unauthorized("Invalid access token")

    user_id = payload.get("sub")

    if not user_id:
        raise unauthorized("Invalid token")

    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise unauthorized("User not found")

    if user.status != UserStatus.ACTIVE:
        raise unauthorized("User account is not active")

    return user


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
