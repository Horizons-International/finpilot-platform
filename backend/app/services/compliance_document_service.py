"""Use-case logic for tenant-isolated compliance documents and approvals."""

import hashlib
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.models.compliance_document import (
    ComplianceApprovalStatus,
    ComplianceDocument,
    ComplianceDocumentApproval,
    ComplianceDocumentStatus,
    ComplianceDocumentVersion,
    ComplianceEvidenceRecord,
)
from app.models.file import File
from app.models.user import User
from app.repositories.compliance_document_repository import (
    ComplianceDocumentRepository,
)
from app.schemas.compliance_document import ComplianceEvidenceCreate
from app.services.file_service import FileService
from app.storages.base_storage import BaseStorage
from app.utils.enums import UserRole

DOCUMENT_CATEGORIES = {"SECURITY", "COMPLIANCE", "OPERATIONS", "OTHER"}
ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "text/plain",
    "text/markdown",
    "image/png",
    "image/jpeg",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.oasis.opendocument.text",
    "text/csv",
}
WRITER_ROLES = {
    UserRole.ADMINISTRATOR.value,
    UserRole.ORGANIZATION_ADMIN.value,
    UserRole.COMPLIANCE_MANAGER.value,
    UserRole.COMPLIANCE_OFFICER.value,
}
APPROVER_ROLES = {
    UserRole.ADMINISTRATOR.value,
    UserRole.ORGANIZATION_ADMIN.value,
    UserRole.COMPLIANCE_MANAGER.value,
}


def _role_value(user: User) -> str:
    role = user.role
    return str(getattr(role, "value", role))


class ComplianceDocumentService:
    def __init__(
        self,
        db: Session,
        *,
        tenant_id: UUID,
        current_user: User,
        file_service: FileService,
        storage: BaseStorage,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        if tenant_id != current_user.tenant_id:
            raise ValueError(
                "Compliance document tenant must match the authenticated user."
            )
        self.db = db
        self.tenant_id = tenant_id
        self.current_user = current_user
        self.file_service = file_service
        self.storage = storage
        self.ip_address = ip_address
        self.user_agent = user_agent
        self.repository = ComplianceDocumentRepository(db, tenant_id)

    def _require_writer(self) -> None:
        if _role_value(self.current_user) not in WRITER_ROLES:
            raise HTTPException(
                status_code=403, detail="Compliance document write access required."
            )

    def _require_approver(self) -> None:
        if _role_value(self.current_user) not in APPROVER_ROLES:
            raise HTTPException(
                status_code=403, detail="Compliance approval permission required."
            )

    def _get_document(self, document_id: UUID) -> ComplianceDocument:
        document = self.repository.get_by_id(document_id)
        if document is None:
            # Do not reveal whether another tenant owns the requested document.
            raise HTTPException(
                status_code=404, detail="Compliance document not found."
            )
        return document

    def _require_owner_or_manager(self, document: ComplianceDocument) -> None:
        if document.owner != self.current_user.id and _role_value(
            self.current_user
        ) not in {
            UserRole.ADMINISTRATOR.value,
            UserRole.ORGANIZATION_ADMIN.value,
            UserRole.COMPLIANCE_MANAGER.value,
        }:
            raise HTTPException(
                status_code=403, detail="You cannot change this document."
            )

    async def _store_uploaded_version(
        self,
        *,
        document: ComplianceDocument,
        file: UploadFile,
        version_number: int,
        change_summary: str | None,
    ) -> ComplianceDocumentVersion:
        if file.content_type not in ALLOWED_CONTENT_TYPES:
            raise HTTPException(
                status_code=415,
                detail="Unsupported content type for compliance documentation.",
            )
        if not file.filename:
            raise HTTPException(
                status_code=400, detail="Uploaded file must have a filename."
            )

        # Hash the file bytes, then rewind for the shared storage service.
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")
        content_sha256 = hashlib.sha256(content).hexdigest()
        await file.seek(0)

        file_record = None
        try:
            file_record = await self.file_service.upload_file(
                file=file,
                uploaded_by=self.current_user.id,
                email=str(self.current_user.email),
                module="compliance",
                folder=str(document.id),
                commit=False,
                allowed_file_types=ALLOWED_CONTENT_TYPES,
                ip_address=self.ip_address,
                user_agent=self.user_agent,
            )
            version_row = ComplianceDocumentVersion(
                tenant_id=self.tenant_id,
                document_id=document.id,
                version=version_number,
                file_id=file_record.id,
                content_sha256=content_sha256,
                change_summary=(
                    (change_summary.strip() or None) if change_summary else None
                ),
                uploaded_by=self.current_user.id,
            )
            self.db.add(version_row)
            self.db.flush()
            return version_row
        except Exception:
            self.db.rollback()
            if file_record is not None:
                try:
                    if self.storage.exists(file_record.storage_path):
                        self.storage.delete(file_record.storage_path)
                except Exception:
                    # Preserve the original DB/service exception.
                    pass
            raise

    async def create_document(
        self,
        *,
        name: str,
        category: str,
        file: UploadFile,
        change_summary: str | None = None,
    ) -> ComplianceDocument:
        self._require_writer()
        normalized_category = category.strip().upper()
        normalized_name = name.strip()
        if normalized_category not in DOCUMENT_CATEGORIES:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Category must be one of: "
                    f"{', '.join(sorted(DOCUMENT_CATEGORIES))}."
                ),
            )
        if not normalized_name:
            raise HTTPException(status_code=422, detail="Document name is required.")

        document = ComplianceDocument(
            tenant_id=self.tenant_id,
            name=normalized_name,
            category=normalized_category,
            version=1,
            status=ComplianceDocumentStatus.DRAFT,
            owner=self.current_user.id,
        )
        file_record = None
        try:
            self.db.add(document)
            self.db.flush()
            version_row = await self._store_uploaded_version(
                document=document,
                file=file,
                version_number=1,
                change_summary=change_summary or "Initial version",
            )
            file_record = self.db.get(File, version_row.file_id)
            self.db.commit()
            self.db.refresh(document)
            return document
        except Exception:
            self.db.rollback()
            if file_record is not None:
                try:
                    if self.storage.exists(file_record.storage_path):
                        self.storage.delete(file_record.storage_path)
                except Exception:
                    pass
            raise

    def list_documents(
        self,
        *,
        category: str | None,
        status_filter: ComplianceDocumentStatus | None,
        limit: int,
        offset: int,
    ) -> list[ComplianceDocument]:
        self._require_reader()
        if category and category.upper() not in DOCUMENT_CATEGORIES:
            raise HTTPException(
                status_code=422,
                detail="Unknown compliance document category.",
            )
        return self.repository.list_documents(
            category=category.upper() if category else None,
            status=status_filter.value if status_filter else None,
            limit=limit,
            offset=offset,
        )

    def _require_reader(self) -> None:
        reader_roles = {role.value for role in UserRole}
        if _role_value(self.current_user) not in reader_roles:
            raise HTTPException(
                status_code=403, detail="Compliance document read access required."
            )

    def get_document(self, document_id: UUID) -> ComplianceDocument:
        self._require_reader()
        return self._get_document(document_id)

    def list_versions(self, document_id: UUID) -> list[ComplianceDocumentVersion]:
        self._require_reader()
        self._get_document(document_id)
        return self.repository.list_versions(document_id)

    async def create_version(
        self,
        *,
        document_id: UUID,
        file: UploadFile,
        change_summary: str | None,
    ) -> ComplianceDocument:
        self._require_writer()
        document = self._get_document(document_id)
        self._require_owner_or_manager(document)
        if document.status == ComplianceDocumentStatus.IN_REVIEW:
            raise HTTPException(
                status_code=409,
                detail="A document cannot be versioned while approval is pending.",
            )
        if document.status == ComplianceDocumentStatus.ARCHIVED:
            raise HTTPException(
                status_code=409, detail="Archived documents cannot be versioned."
            )

        next_version = document.version + 1
        file_record = None
        try:
            version_row = await self._store_uploaded_version(
                document=document,
                file=file,
                version_number=next_version,
                change_summary=change_summary,
            )
            file_record = self.db.get(File, version_row.file_id)
            document.version = next_version
            document.status = ComplianceDocumentStatus.DRAFT
            self.db.add(document)
            self.db.commit()
            self.db.refresh(document)
            return document
        except Exception:
            self.db.rollback()
            if file_record is not None:
                try:
                    if self.storage.exists(file_record.storage_path):
                        self.storage.delete(file_record.storage_path)
                except Exception:
                    pass
            raise

    def submit_for_approval(
        self, document_id: UUID, comment: str | None
    ) -> ComplianceDocument:
        self._require_writer()
        document = self._get_document(document_id)
        self._require_owner_or_manager(document)
        if document.status not in {
            ComplianceDocumentStatus.DRAFT,
            ComplianceDocumentStatus.REJECTED,
        }:
            raise HTTPException(
                status_code=409,
                detail="Only draft or rejected documents can be submitted.",
            )
        prior_approvals = self.repository.list_approvals(document.id)
        if (
            document.status == ComplianceDocumentStatus.REJECTED
            and prior_approvals
            and prior_approvals[0].status == ComplianceApprovalStatus.REJECTED
            and prior_approvals[0].version == document.version
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    "Upload a new document version after rejection before resubmitting."
                ),
            )
        if self.repository.get_version(document.id, document.version) is None:
            raise HTTPException(
                status_code=409,
                detail="A document version must exist before approval.",
            )

        approval = ComplianceDocumentApproval(
            tenant_id=self.tenant_id,
            document_id=document.id,
            version=document.version,
            status=ComplianceApprovalStatus.PENDING,
            requested_by=self.current_user.id,
            request_comment=comment,
        )
        document.status = ComplianceDocumentStatus.IN_REVIEW
        self.db.add(approval)
        self.db.add(document)
        self.db.commit()
        self.db.refresh(document)
        return document

    def _review(
        self,
        document_id: UUID,
        comment: str | None,
        decision: ComplianceApprovalStatus,
    ) -> ComplianceDocument:
        self._require_approver()
        document = self._get_document(document_id)
        if document.owner == self.current_user.id:
            raise HTTPException(
                status_code=403,
                detail="The document owner cannot approve their own document.",
            )
        approval = self.repository.pending_approval(document.id)
        if approval is None or document.status != ComplianceDocumentStatus.IN_REVIEW:
            raise HTTPException(
                status_code=409,
                detail="No pending approval exists for this document.",
            )
        if approval.version != document.version:
            raise HTTPException(
                status_code=409,
                detail="Approval request is not for the current document version.",
            )

        approval.status = decision
        approval.reviewed_by = self.current_user.id
        approval.review_comment = comment
        approval.reviewed_at = datetime.now(timezone.utc)
        document.status = (
            ComplianceDocumentStatus.APPROVED
            if decision == ComplianceApprovalStatus.APPROVED
            else ComplianceDocumentStatus.REJECTED
        )
        self.db.add(approval)
        self.db.add(document)
        self.db.commit()
        self.db.refresh(document)
        return document

    def approve(self, document_id: UUID, comment: str | None) -> ComplianceDocument:
        return self._review(document_id, comment, ComplianceApprovalStatus.APPROVED)

    def reject(self, document_id: UUID, comment: str | None) -> ComplianceDocument:
        if not comment or not comment.strip():
            raise HTTPException(
                status_code=422, detail="A rejection comment is required."
            )
        return self._review(
            document_id, comment.strip(), ComplianceApprovalStatus.REJECTED
        )

    def list_approvals(self, document_id: UUID) -> list[ComplianceDocumentApproval]:
        self._require_reader()
        self._get_document(document_id)
        return self.repository.list_approvals(document_id)

    def add_evidence(
        self,
        document_id: UUID,
        payload: ComplianceEvidenceCreate,
        *,
        allowed_evidence_types: set[str],
    ) -> ComplianceEvidenceRecord:
        self._require_writer()
        document = self._get_document(document_id)
        version_row = None
        if payload.version is not None:
            version_row = self.repository.get_version(document.id, payload.version)
            if version_row is None:
                raise HTTPException(
                    status_code=404,
                    detail="Compliance document version not found.",
                )
        evidence_type = str(payload.evidence_type)
        if evidence_type not in allowed_evidence_types:
            raise HTTPException(status_code=422, detail="Unknown evidence type.")
        if not payload.description.strip() or not payload.source_reference.strip():
            raise HTTPException(
                status_code=422,
                detail="Evidence description and source reference are required.",
            )
        collected_at = payload.collected_at or datetime.now(timezone.utc)
        if collected_at.tzinfo is None:
            collected_at = collected_at.replace(tzinfo=timezone.utc)
        evidence = ComplianceEvidenceRecord(
            tenant_id=self.tenant_id,
            document_id=document.id,
            version_id=version_row.id if version_row else None,
            evidence_type=evidence_type,
            description=payload.description.strip(),
            source_reference=payload.source_reference.strip(),
            collected_by=self.current_user.id,
            collected_at=collected_at,
        )
        self.db.add(evidence)
        self.db.commit()
        self.db.refresh(evidence)
        return evidence

    def list_evidence(self, document_id: UUID) -> list[ComplianceEvidenceRecord]:
        self._require_reader()
        self._get_document(document_id)
        return self.repository.list_evidence(document_id)

    def archive(self, document_id: UUID) -> ComplianceDocument:
        self._require_approver()
        document = self._get_document(document_id)
        if document.status == ComplianceDocumentStatus.IN_REVIEW:
            raise HTTPException(
                status_code=409,
                detail="A document cannot be archived while approval is pending.",
            )
        document.status = ComplianceDocumentStatus.ARCHIVED
        self.db.add(document)
        self.db.commit()
        self.db.refresh(document)
        return document
