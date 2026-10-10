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
from app.services.tenant_access_audit import deny_tenant_access
from app.storages.base_storage import BaseStorage
from app.utils.constants import DOCUMENT_ALLOWED_FILE_TYPES
from app.utils.enums import AuditEventType, DocumentStatus
from app.utils.errors import bad_request, not_found


class DocumentService:
    def __init__(
        self,
        db: Session,
        storage: BaseStorage,
        *,
        tenant_id: UUID,
        actor_user_id: UUID | None = None,
        actor_email: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.actor_user_id = actor_user_id
        self.actor_email = actor_email
        self.ip_address = ip_address
        self.user_agent = user_agent

        self.repository = CustomerDocumentRepository(
            db,
            tenant_id,
        )
        self.audit_service = AuditService(db)
        self.file_service = FileService(
            db=db,
            storage=storage,
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            actor_email=actor_email,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.storage = storage

        self.audit_service = AuditService(db)

        self.file_service = FileService(
            db=db,
            storage=storage,
            tenant_id=tenant_id,
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
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> CustomerDocument:
        # ---------------------------------------------------------
        # 1. Verify customer exists
        # ---------------------------------------------------------
        customer = (
            self.db.query(Customer)
            .filter(
                Customer.id == customer_id,
                Customer.tenant_id == self.tenant_id,
            )
            .first()
        )

        if customer is None:
            deny_tenant_access(
                self.db,
                user_id=self.actor_user_id,
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
                resource_type="customer",
                resource_id=customer_id,
                resource_name="Customer",
            )

        # ---------------------------------------------------------
        # 2. Verify verification case exists and belongs to customer
        # ---------------------------------------------------------
        verification_case = (
            self.db.query(IdentityVerificationCase)
            .filter(
                IdentityVerificationCase.id == verification_case_id,
                IdentityVerificationCase.customer_id == customer_id,
                IdentityVerificationCase.tenant_id == self.tenant_id,
            )
            .first()
        )

        if verification_case is None:
            deny_tenant_access(
                self.db,
                user_id=self.actor_user_id,
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
                resource_type="verification_case",
                resource_id=verification_case_id,
                resource_name="Verification case",
            )

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
            ip_address=ip_address,
            user_agent=user_agent,
        )

        try:
            # -----------------------------------------------------
            # 5. Create CustomerDocument metadata
            # -----------------------------------------------------
            document = CustomerDocument(
                customer_id=customer_id,
                tenant_id=self.tenant_id,
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
                ip_address=ip_address,
                user_agent=user_agent,
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

        customer = (
            self.db.query(Customer)
            .filter(
                Customer.id == customer_id,
                Customer.tenant_id == self.tenant_id,
            )
            .first()
        )

        if customer is None:
            deny_tenant_access(
                self.db,
                user_id=self.actor_user_id,
                email=self.actor_email,
                ip_address=self.ip_address,
                user_agent=self.user_agent,
                resource_type="customer",
                resource_id=customer_id,
                resource_name="Customer",
            )

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
                IdentityVerificationCase.tenant_id == self.tenant_id,
            )
            .first()
        )

        if verification_case is None:
            deny_tenant_access(
                self.db,
                user_id=self.actor_user_id,
                email=self.actor_email,
                ip_address=self.ip_address,
                user_agent=self.user_agent,
                resource_type="verification_case",
                resource_id=verification_case_id,
                resource_name="Verification case",
            )

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
            deny_tenant_access(
                self.db,
                user_id=self.actor_user_id,
                email=self.actor_email,
                ip_address=self.ip_address,
                user_agent=self.user_agent,
                resource_type="customer_document",
                resource_id=document_id,
                resource_name="Customer Document",
            )

        return document
