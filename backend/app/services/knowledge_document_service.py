from uuid import UUID

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.models.knowledge_document import KnowledgeDocument
from app.repositories.knowledge_document_repository import (
    KnowledgeDocumentRepository,
)
from app.schemas.knowledge_document import (
    KnowledgeDocumentVersionCreate,
)
from app.services.audit_service import AuditService
from app.services.file_service import FileService
from app.utils.enums import (
    AuditEventType,
    KnowledgeDocumentCategory,
    KnowledgeDocumentStatus,
)
from app.utils.errors import bad_request, not_found


class KnowledgeDocumentService:
    def __init__(
        self,
        db: Session,
        file_service: FileService,
    ) -> None:
        self.db = db
        self.repository = KnowledgeDocumentRepository(db)
        self.file_service = file_service
        self.audit_service = AuditService(db)

    async def create_document(
        self,
        name: str,
        category: KnowledgeDocumentCategory,
        file: UploadFile,
        uploaded_by: UUID,
        email: str,
    ):
        name = name.strip()

        if not name:
            raise bad_request("Document name is required.")

        existing_document = self.repository.get_latest_by_name(name)

        if existing_document is not None:
            raise bad_request(
                f"A knowledge document named '{name}' already exists. "
                "Create a new version instead."
            )

        stored_file = None

        try:
            stored_file = await self.file_service.upload_file(
                file=file,
                uploaded_by=uploaded_by,
                email=email,
                module="knowledge_base",
                folder="knowledge",
                commit=False,
            )

            document = KnowledgeDocument(
                name=name,
                category=category.value,
                file_reference=str(stored_file.id),
                version=1,
                status=KnowledgeDocumentStatus.INACTIVE,
                uploaded_by=uploaded_by,
            )

            self.repository.create(document)

            self.audit_service.log_event(
                event_type=AuditEventType.KNOWLEDGE_DOCUMENT_CREATED,
                user_id=uploaded_by,
                email=email,
                resource_type="knowledge_document",
                resource_id=document.id,
            )

            self.db.commit()
            self.db.refresh(document)

            return document

        except Exception:
            self.db.rollback()

            if stored_file is not None:
                try:
                    self.file_service.delete_file(
                        stored_file.id,
                        uploaded_by,
                        email,
                    )
                except Exception:
                    pass

            raise

    async def create_version(
        self,
        document_id: UUID,
        file: UploadFile,
        uploaded_by: UUID,
        email: str,
        data: KnowledgeDocumentVersionCreate,
    ):
        from app.models.knowledge_document import KnowledgeDocument

        latest_document = self.repository.get_by_id(document_id)

        if latest_document is None:
            raise not_found("Knowledge document")

        name = data.name.strip() if data.name else latest_document.name

        category = (
            data.category.value
            if data.category is not None
            else latest_document.category
        )

        latest_version = self.repository.get_latest_by_name(name)

        if latest_version is None:
            raise bad_request("Unable to determine the latest document version.")

        next_version = latest_version.version + 1

        stored_file = None

        try:
            stored_file = await self.file_service.upload_file(
                file=file,
                uploaded_by=uploaded_by,
                email=email,
                module="knowledge_base",
                folder="knowledge",
                commit=False,
            )

            document = KnowledgeDocument(
                name=name,
                category=category,
                file_reference=str(stored_file.id),
                version=next_version,
                status=KnowledgeDocumentStatus.INACTIVE,
                uploaded_by=uploaded_by,
            )

            self.repository.create(document)

            self.audit_service.log_event(
                event_type=AuditEventType.KNOWLEDGE_DOCUMENT_VERSION_CREATED,
                user_id=uploaded_by,
                email=email,
                resource_type="knowledge_document",
                resource_id=document.id,
            )

            self.db.commit()
            self.db.refresh(document)

            return document

        except Exception:
            self.db.rollback()

            if stored_file is not None:
                try:
                    self.file_service.delete_file(
                        stored_file.id,
                        uploaded_by,
                        email,
                    )
                except Exception:
                    pass

            raise

    def get_document(
        self,
        document_id: UUID,
    ):
        document = self.repository.get_by_id(document_id)

        if document is None:
            raise not_found("Knowledge document")

        return document

    def get_documents(self):
        return self.repository.get_all_ordered()

    def get_versions(
        self,
        document_id: UUID,
    ):
        document = self.repository.get_by_id(document_id)

        if document is None:
            raise not_found("Knowledge document")

        return self.repository.get_all_versions(
            document.name,
        )

    def activate_document(
        self,
        document_id: UUID,
        uploaded_by: UUID,
        email: str,
    ):
        document = self.repository.get_by_id(document_id)

        if document is None:
            raise not_found("Knowledge document")

        if document.status == KnowledgeDocumentStatus.ACTIVE:
            raise bad_request("The knowledge document is already active.")

        active_document = self.repository.get_active_by_name(
            document.name,
        )

        if active_document is not None:
            raise bad_request(
                "Another version of this document is already active. "
                "Deactivate it before activating this version."
            )

        document.status = KnowledgeDocumentStatus.ACTIVE

        self.repository.update(document)

        self.audit_service.log_event(
            event_type=AuditEventType.KNOWLEDGE_DOCUMENT_ACTIVATED,
            user_id=uploaded_by,
            email=email,
            resource_type="knowledge_document",
            resource_id=document.id,
        )

        self.db.commit()
        self.db.refresh(document)

        return document

    def deactivate_document(
        self,
        document_id: UUID,
        uploaded_by: UUID,
        email: str,
    ):
        document = self.repository.get_by_id(document_id)

        if document is None:
            raise not_found("Knowledge document")

        if document.status == KnowledgeDocumentStatus.INACTIVE:
            raise bad_request("The knowledge document is already inactive.")

        document.status = KnowledgeDocumentStatus.INACTIVE

        self.repository.update(document)

        self.audit_service.log_event(
            event_type=AuditEventType.KNOWLEDGE_DOCUMENT_DEACTIVATED,
            user_id=uploaded_by,
            email=email,
            resource_type="knowledge_document",
            resource_id=document.id,
        )

        self.db.commit()
        self.db.refresh(document)

        return document
