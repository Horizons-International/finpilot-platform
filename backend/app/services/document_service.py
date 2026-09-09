from uuid import UUID

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.customer_audit_log import CustomerAuditLog
from app.models.document import CustomerDocument
from app.models.verification_case import IdentityVerificationCase
from app.models.verification_document_type import VerificationDocumentType
from app.repositories.document_repository import CustomerDocumentRepository
from app.services.audit_service import AuditService
from app.services.document_validation import DocumentValidationService
from app.services.file_service import FileService
from app.storages.base_storage import BaseStorage
from app.utils.constants import DOCUMENT_ALLOWED_FILE_TYPES
from app.utils.enums import AuditEventType, DocumentStatus
from app.utils.errors import bad_request, not_found


class DocumentService:
    def __init__(
        self,
        db: Session,
        storage: BaseStorage,
    ) -> None:
        self.db = db
        self.repository = CustomerDocumentRepository(db)
        self.audit_service = AuditService(db)
        self.file_service = FileService(
            db=db,
            storage=storage,
        )
        self.storage = storage

    async def upload_document(
        self,
        customer_id: UUID,
        verification_case_id: UUID,
        document_type_id: UUID,
        file: UploadFile,
        user_id: UUID,
        email: str,
    ) -> CustomerDocument:
        # ---------------------------------------------------------
        # 1. Verify customer exists
        # ---------------------------------------------------------
        customer = self.db.query(Customer).filter(Customer.id == customer_id).first()

        if customer is None:
            raise not_found("Customer")

        # ---------------------------------------------------------
        # 2. Verify verification case exists and belongs to customer
        # ---------------------------------------------------------
        verification_case = (
            self.db.query(IdentityVerificationCase)
            .filter(
                IdentityVerificationCase.id == verification_case_id,
                IdentityVerificationCase.customer_id == customer_id,
            )
            .first()
        )

        if verification_case is None:
            raise not_found("Verification case")

        # ---------------------------------------------------------
        # 3. Verify document type exists and is active
        # ---------------------------------------------------------
        document_type = (
            self.db.query(VerificationDocumentType)
            .filter(
                VerificationDocumentType.id == document_type_id,
            )
            .first()
        )

        if document_type is None:
            raise not_found("Verification document type")

        if not document_type.is_active:
            raise bad_request("Verification document type is inactive.")

        DocumentValidationService.validate_document_type(document_type_id)

        # ---------------------------------------------------------
        # 4. Upload physical file + File metadata
        #
        # IMPORTANT:
        # commit=False keeps everything in the current transaction.
        # ---------------------------------------------------------
        file_record = await self.file_service.upload_file(
            file=file,
            uploaded_by=user_id,
            email=email,
            module="verification",
            folder=str(customer_id),
            commit=False,
            allowed_file_types=DOCUMENT_ALLOWED_FILE_TYPES,
        )

        try:
            # -----------------------------------------------------
            # 5. Create CustomerDocument metadata
            # -----------------------------------------------------
            document = CustomerDocument(
                customer_id=customer_id,
                verification_case_id=verification_case_id,
                document_type_id=document_type_id,
                file_reference=str(file_record.id),
                file_name=file_record.original_filename,
                file_type=file_record.content_type,
                file_size=file_record.file_size,
                status=DocumentStatus.UPLOADED,
                uploaded_by=user_id,
            )

            document = self.repository.create(document)

            # -----------------------------------------------------
            # 6. Detailed customer audit
            # -----------------------------------------------------
            customer_audit_log = CustomerAuditLog(
                customer_id=customer_id,
                user_id=user_id,
                resource_type="customer_document",
                resource_id=document.id,
                action="UPLOAD DOCUMENT",
                old_value=None,
                new_value={
                    "verification_case_id": str(verification_case_id),
                    "document_type_id": str(document_type_id),
                    "file_reference": str(file_record.id),
                    "file_name": file_record.original_filename,
                    "file_type": file_record.content_type,
                    "file_size": file_record.file_size,
                    "status": document.status.value,
                },
            )

            self.db.add(customer_audit_log)
            self.db.flush()

            # -----------------------------------------------------
            # 7. General audit
            # -----------------------------------------------------
            self.audit_service.log_event(
                event_type=AuditEventType.CUSTOMER_DOCUMENT_CREATED,
                user_id=user_id,
                email=email,
                resource_type="customer_document",
                resource_id=document.id,
            )

            # -----------------------------------------------------
            # 8. Commit File + CustomerDocument + audits together
            # -----------------------------------------------------
            self.db.commit()
            self.db.refresh(document)

            return document

        except Exception:
            # Roll back File metadata, CustomerDocument metadata,
            # and audit records.
            self.db.rollback()

            # FileService already created the physical file, so
            # remove it when the downstream document transaction fails.
            try:
                if self.storage.exists(file_record.storage_path):
                    self.storage.delete(file_record.storage_path)
            except Exception:
                # Do not hide the original exception if physical
                # cleanup itself fails.
                pass

            raise

    def get_documents_by_customer(
        self,
        customer_id: UUID,
    ) -> list[CustomerDocument]:
        customer = self.db.query(Customer).filter(Customer.id == customer_id).first()

        if customer is None:
            raise not_found("Customer")

        return self.repository.get_by_customer_id(customer_id)

    def get_documents_by_case(
        self,
        customer_id: UUID,
        verification_case_id: UUID,
    ) -> list[CustomerDocument]:
        verification_case = (
            self.db.query(IdentityVerificationCase)
            .filter(
                IdentityVerificationCase.id == verification_case_id,
                IdentityVerificationCase.customer_id == customer_id,
            )
            .first()
        )

        if verification_case is None:
            raise not_found("Verification case")

        return self.repository.get_by_verification_case_id(verification_case_id)

    def get_document(
        self,
        customer_id: UUID,
        verification_case_id: UUID,
        document_id: UUID,
    ) -> CustomerDocument:
        document = self.repository.get_by_id_and_case(
            document_id=document_id,
            customer_id=customer_id,
            verification_case_id=verification_case_id,
        )

        if document is None:
            raise not_found("Customer document")

        return document
