"""Tenant-scoped retention, legal hold, and approved data erasure workflow."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, cast

from sqlalchemy import Table, delete, exists, select
from sqlalchemy.orm import Session

from app.core.data_protection import DataProtectionError
from app.core.database import Base
from app.models.compliance_case import ComplianceCase
from app.models.customer import Customer
from app.models.data_protection import (
    DataDeletionRequest,
    DataDeletionStatus,
    DataLegalHold,
    DataProtectionAuditEvent,
    DataProtectionPolicy,
    DataResourceType,
)
from app.models.document import CustomerDocument
from app.models.file import File
from app.models.verification_case import IdentityVerificationCase
from app.repositories.data_protection_repository import DataProtectionRepository
from app.storages.base_storage import BaseStorage


class DataProtectionService:
    ALLOWED_RESOURCE_TYPES = {item.value for item in DataResourceType}
    RETENTION_SYSTEM_ACTOR = uuid.UUID(int=0)

    def __init__(
        self, db: Session, tenant_id: uuid.UUID, storage: BaseStorage | None = None
    ) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.storage = storage
        self.repo = DataProtectionRepository(db, tenant_id)

    def _validate_resource_type(self, resource_type: str) -> str:
        normalized = resource_type.upper()
        if normalized not in self.ALLOWED_RESOURCE_TYPES:
            raise DataProtectionError(f"Unsupported resource_type: {resource_type}")
        return normalized

    def _audit(
        self,
        action: str,
        actor_id: uuid.UUID | None,
        resource_type: str,
        resource_id: uuid.UUID | None,
        details: dict | None = None,
    ) -> None:
        self.db.add(
            DataProtectionAuditEvent(
                tenant_id=self.tenant_id,
                actor_id=actor_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                details=details or {},
            )
        )

    def set_policy(
        self,
        resource_type: str,
        retention_days: int,
        enabled: bool,
        legal_basis: str | None,
        actor_id: uuid.UUID,
    ) -> DataProtectionPolicy:
        resource_type = self._validate_resource_type(resource_type)
        if not 1 <= retention_days <= 36500:
            raise DataProtectionError("retention_days must be between 1 and 36500")
        if legal_basis is not None and not legal_basis.strip():
            raise DataProtectionError("legal_basis cannot be blank")

        policy = self.repo.get_policy(resource_type)
        if policy is None:
            policy = DataProtectionPolicy(
                tenant_id=self.tenant_id,
                resource_type=resource_type,
                retention_days=retention_days,
                enabled=enabled,
                legal_basis=legal_basis.strip() if legal_basis else None,
                updated_by=actor_id,
            )
            self.db.add(policy)
        else:
            policy.retention_days = retention_days
            policy.enabled = enabled
            policy.legal_basis = legal_basis.strip() if legal_basis else None
            policy.updated_by = actor_id
        self.db.flush()
        self._audit(
            "RETENTION_POLICY_UPDATED",
            actor_id,
            resource_type,
            policy.id,
            {
                "retention_days": retention_days,
                "enabled": enabled,
            },
        )
        return policy

    def create_legal_hold(
        self,
        resource_type: str,
        resource_id: uuid.UUID,
        reason: str,
        actor_id: uuid.UUID,
    ) -> DataLegalHold:
        resource_type = self._validate_resource_type(resource_type)
        if not reason.strip():
            raise DataProtectionError("A legal-hold reason is required")
        if not self._resource_exists(resource_type, resource_id):
            raise DataProtectionError("Resource not found in the current tenant")
        if self.repo.active_hold(resource_type, resource_id):
            raise DataProtectionError("An active legal hold already exists")
        hold = DataLegalHold(
            tenant_id=self.tenant_id,
            resource_type=resource_type,
            resource_id=resource_id,
            reason=reason.strip(),
            active=True,
            created_by=actor_id,
        )
        self.db.add(hold)
        self.db.flush()
        self._audit(
            "LEGAL_HOLD_CREATED",
            actor_id,
            resource_type,
            resource_id,
            {"hold_id": str(hold.id)},
        )
        return hold

    def release_legal_hold(
        self, hold_id: uuid.UUID, actor_id: uuid.UUID
    ) -> DataLegalHold:
        hold = self.db.scalar(
            select(DataLegalHold).where(
                DataLegalHold.id == hold_id,
                DataLegalHold.tenant_id == self.tenant_id,
                DataLegalHold.active.is_(True),
            )
        )
        if hold is None:
            raise DataProtectionError("Active legal hold not found")
        hold.active = False
        hold.released_by = actor_id
        hold.released_at = datetime.now(timezone.utc)
        self._audit(
            "LEGAL_HOLD_RELEASED",
            actor_id,
            hold.resource_type,
            hold.resource_id,
            {"hold_id": str(hold.id)},
        )
        self.db.flush()
        return hold

    def request_deletion(
        self,
        resource_type: str,
        resource_id: uuid.UUID,
        reason: str,
        actor_id: uuid.UUID,
    ) -> DataDeletionRequest:
        resource_type = self._validate_resource_type(resource_type)
        if not reason.strip():
            raise DataProtectionError("A deletion reason is required")
        if not self._resource_exists(resource_type, resource_id):
            raise DataProtectionError("Resource not found in the current tenant")
        self._assert_no_holds(resource_type, resource_id)
        request = DataDeletionRequest(
            tenant_id=self.tenant_id,
            resource_type=resource_type,
            resource_id=resource_id,
            status=DataDeletionStatus.REQUESTED,
            requested_by=actor_id,
            reason=reason.strip(),
        )
        self.db.add(request)
        self.db.flush()
        self._audit(
            "DELETION_REQUESTED",
            actor_id,
            resource_type,
            resource_id,
            {"request_id": str(request.id)},
        )
        return request

    def approve_deletion(
        self, request_id: uuid.UUID, actor_id: uuid.UUID
    ) -> DataDeletionRequest:
        request = self.repo.get_deletion_request(request_id)
        if request is None:
            raise DataProtectionError("Deletion request not found")
        if request.status != DataDeletionStatus.REQUESTED:
            raise DataProtectionError("Deletion request is not awaiting approval")
        if request.requested_by == actor_id:
            raise DataProtectionError(
                "A different administrator must approve the deletion request"
            )
        self._assert_no_holds(request.resource_type, request.resource_id)
        request.status = DataDeletionStatus.APPROVED
        request.approved_by = actor_id
        request.approved_at = datetime.now(timezone.utc)
        request.failure_reason = None
        self._audit(
            "DELETION_APPROVED",
            actor_id,
            request.resource_type,
            request.resource_id,
            {"request_id": str(request.id)},
        )
        self.db.flush()
        return request

    def execute_deletion(self, request_id: uuid.UUID) -> DataDeletionRequest:
        request = self.repo.get_deletion_request(request_id)
        if request is None:
            raise DataProtectionError("Deletion request not found")
        if request.status not in {
            DataDeletionStatus.APPROVED,
            DataDeletionStatus.STORAGE_CLEANUP,
        }:
            raise DataProtectionError("Deletion request is not executable")
        self._assert_no_holds(request.resource_type, request.resource_id)

        # Persist a retryable state before touching external storage. A process crash
        # after this commit can safely retry because LocalStorage.delete is idempotent.
        request.status = DataDeletionStatus.STORAGE_CLEANUP
        request.failure_reason = None
        self.db.commit()

        try:
            self._delete_storage_for_resource(
                request.resource_type, request.resource_id
            )
            self._delete_database_resource(request.resource_type, request.resource_id)
            request = self.repo.get_deletion_request(request_id)
            if request is None:
                raise DataProtectionError("Deletion request disappeared unexpectedly")
            request.status = DataDeletionStatus.COMPLETED
            request.completed_at = datetime.now(timezone.utc)
            request.failure_reason = None
            self._audit(
                "DELETION_COMPLETED",
                request.approved_by,
                request.resource_type,
                request.resource_id,
                {
                    "request_id": str(request.id),
                },
            )
            self.db.commit()
            return request
        except Exception as exc:
            self.db.rollback()
            retryable = self.repo.get_deletion_request(request_id)
            if retryable is None:
                raise
            # Keep STORAGE_CLEANUP so a retry is possible if a storage provider failed
            # part way through. Do not include sensitive file contents in this field.
            retryable.status = DataDeletionStatus.STORAGE_CLEANUP
            retryable.failure_reason = f"{type(exc).__name__}: {str(exc)}"[:2000]
            self._audit(
                "DELETION_RETRY_REQUIRED",
                retryable.approved_by,
                retryable.resource_type,
                retryable.resource_id,
                {"request_id": str(retryable.id), "error_type": type(exc).__name__},
            )
            self.db.commit()
            return retryable

    def eligible(
        self, resource_type: str, created_at: datetime, now: datetime | None = None
    ) -> bool:
        resource_type = self._validate_resource_type(resource_type)
        policy = self.repo.get_policy(resource_type)
        if policy is None or not policy.enabled:
            return False
        current = now or datetime.now(timezone.utc)
        created = (
            created_at if created_at.tzinfo else created_at.replace(tzinfo=timezone.utc)
        )
        return created <= current - timedelta(days=policy.retention_days)

    def enqueue_expired_candidates(
        self, now: datetime | None = None, limit_per_type: int = 500
    ) -> int:
        """Queue expired records for review; this never approves or deletes them."""
        current = now or datetime.now(timezone.utc)
        model_by_type: dict[str, Any] = {
            DataResourceType.CUSTOMER.value: Customer,
            DataResourceType.DOCUMENT.value: CustomerDocument,
            DataResourceType.VERIFICATION_CASE.value: IdentityVerificationCase,
            DataResourceType.COMPLIANCE_CASE.value: ComplianceCase,
            DataResourceType.FILE.value: File,
        }
        queued = 0
        for resource_type, model in model_by_type.items():
            policy = self.repo.get_policy(resource_type)
            if policy is None or not policy.enabled:
                continue
            cutoff = current - timedelta(days=policy.retention_days)
            already_requested = exists(
                select(DataDeletionRequest.id).where(
                    DataDeletionRequest.tenant_id == self.tenant_id,
                    DataDeletionRequest.resource_type == resource_type,
                    DataDeletionRequest.resource_id == model.id,
                    DataDeletionRequest.status.in_(
                        [
                            DataDeletionStatus.REQUESTED,
                            DataDeletionStatus.APPROVED,
                            DataDeletionStatus.STORAGE_CLEANUP,
                            DataDeletionStatus.COMPLETED,
                        ]
                    ),
                )
            )
            records = self.db.scalars(
                select(model)
                .where(
                    model.tenant_id == self.tenant_id,
                    model.created_at <= cutoff,
                    ~already_requested,
                )
                .order_by(model.created_at)
                .limit(limit_per_type)
            ).all()
            for record in records:
                resource_id = record.id
                if resource_type == DataResourceType.FILE.value:
                    referenced_document = self.db.scalar(
                        select(CustomerDocument.id)
                        .where(
                            CustomerDocument.tenant_id == self.tenant_id,
                            CustomerDocument.file_reference == str(resource_id),
                        )
                        .limit(1)
                    )
                    if referenced_document is not None:
                        # The document policy owns cleanup of its associated file.
                        continue
                if not self._resource_exists(resource_type, resource_id):
                    continue
                if self._has_pending_deletion(resource_type, resource_id):
                    continue
                try:
                    self._assert_no_holds(resource_type, resource_id)
                except DataProtectionError:
                    continue
                request = DataDeletionRequest(
                    tenant_id=self.tenant_id,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    status=DataDeletionStatus.REQUESTED,
                    requested_by=None,
                    reason="Retention period elapsed; awaiting authorized review.",
                )
                self.db.add(request)
                self.db.flush()
                self._audit(
                    "RETENTION_DELETION_QUEUED",
                    None,
                    resource_type,
                    resource_id,
                    {
                        "request_id": str(request.id),
                        "retention_days": policy.retention_days,
                    },
                )
                queued += 1
        self.db.commit()
        return queued

    def _has_pending_deletion(self, resource_type: str, resource_id: uuid.UUID) -> bool:
        return (
            self.db.scalar(
                select(DataDeletionRequest.id)
                .where(
                    DataDeletionRequest.tenant_id == self.tenant_id,
                    DataDeletionRequest.resource_type == resource_type,
                    DataDeletionRequest.resource_id == resource_id,
                    DataDeletionRequest.status.in_(
                        [
                            DataDeletionStatus.REQUESTED,
                            DataDeletionStatus.APPROVED,
                            DataDeletionStatus.STORAGE_CLEANUP,
                            DataDeletionStatus.COMPLETED,
                        ]
                    ),
                )
                .limit(1)
            )
            is not None
        )

    def _resource_exists(self, resource_type: str, resource_id: uuid.UUID) -> bool:
        model_by_type: dict[str, Any] = {
            DataResourceType.CUSTOMER.value: Customer,
            DataResourceType.DOCUMENT.value: CustomerDocument,
            DataResourceType.VERIFICATION_CASE.value: IdentityVerificationCase,
            DataResourceType.COMPLIANCE_CASE.value: ComplianceCase,
            DataResourceType.FILE.value: File,
        }
        model = model_by_type[resource_type]
        return (
            self.db.scalar(
                select(model.id).where(
                    model.id == resource_id,
                    model.tenant_id == self.tenant_id,
                )
            )
            is not None
        )

    def _related_ids(
        self, customer_id: uuid.UUID
    ) -> tuple[list[uuid.UUID], list[uuid.UUID], list[uuid.UUID], list[uuid.UUID]]:
        documents = self.db.scalars(
            select(CustomerDocument).where(
                CustomerDocument.tenant_id == self.tenant_id,
                CustomerDocument.customer_id == customer_id,
            )
        ).all()
        document_ids = [row.id for row in documents]
        verification_ids = list(
            self.db.scalars(
                select(IdentityVerificationCase.id).where(
                    IdentityVerificationCase.tenant_id == self.tenant_id,
                    IdentityVerificationCase.customer_id == customer_id,
                )
            ).all()
        )
        compliance_ids = list(
            self.db.scalars(
                select(ComplianceCase.id).where(
                    ComplianceCase.tenant_id == self.tenant_id,
                    ComplianceCase.customer_id == customer_id,
                )
            ).all()
        )
        file_ids: list[uuid.UUID] = []
        for document in documents:
            try:
                file_id = uuid.UUID(document.file_reference)
            except (ValueError, TypeError, AttributeError):
                continue
            found = self.db.scalar(
                select(File.id).where(
                    File.id == file_id, File.tenant_id == self.tenant_id
                )
            )
            if found:
                file_ids.append(found)
        return document_ids, verification_ids, compliance_ids, file_ids

    def _assert_no_holds(self, resource_type: str, resource_id: uuid.UUID) -> None:
        if self.repo.active_hold(resource_type, resource_id):
            raise DataProtectionError("Resource is protected by an active legal hold")

        related: list[tuple[str, list[uuid.UUID]]] = []
        if resource_type == DataResourceType.CUSTOMER.value:
            document_ids, verification_ids, compliance_ids, file_ids = (
                self._related_ids(resource_id)
            )
            related.extend(
                [
                    ("DOCUMENT", document_ids),
                    ("VERIFICATION_CASE", verification_ids),
                    ("COMPLIANCE_CASE", compliance_ids),
                    ("FILE", file_ids),
                ]
            )
        elif resource_type == DataResourceType.DOCUMENT.value:
            document = self.db.scalar(
                select(CustomerDocument).where(
                    CustomerDocument.id == resource_id,
                    CustomerDocument.tenant_id == self.tenant_id,
                )
            )
            if document is not None:
                related.extend(
                    [
                        ("CUSTOMER", [document.customer_id]),
                        ("VERIFICATION_CASE", [document.verification_case_id]),
                    ]
                )
                file_row = self._file_for_document(document)
                if file_row is not None:
                    related.append(("FILE", [file_row.id]))
        elif resource_type == DataResourceType.VERIFICATION_CASE.value:
            case = self.db.scalar(
                select(IdentityVerificationCase).where(
                    IdentityVerificationCase.id == resource_id,
                    IdentityVerificationCase.tenant_id == self.tenant_id,
                )
            )
            if case is not None:
                related.append(("CUSTOMER", [case.customer_id]))
                docs = self.db.scalars(
                    select(CustomerDocument).where(
                        CustomerDocument.tenant_id == self.tenant_id,
                        CustomerDocument.verification_case_id == resource_id,
                    )
                ).all()
                doc_ids = [doc.id for doc in docs]
                file_ids = [
                    file_row.id
                    for doc in docs
                    if (file_row := self._file_for_document(doc)) is not None
                ]
                related.extend([("DOCUMENT", doc_ids), ("FILE", file_ids)])
        elif resource_type == DataResourceType.COMPLIANCE_CASE.value:
            complaince_case = self.db.scalar(
                select(ComplianceCase).where(
                    ComplianceCase.id == resource_id,
                    ComplianceCase.tenant_id == self.tenant_id,
                )
            )
            if complaince_case is not None:
                related.append(("CUSTOMER", [complaince_case.customer_id]))
        elif resource_type == DataResourceType.FILE.value:
            referenced_document = self.db.scalar(
                select(CustomerDocument.id)
                .where(
                    CustomerDocument.tenant_id == self.tenant_id,
                    CustomerDocument.file_reference == str(resource_id),
                )
                .limit(1)
            )
            if referenced_document is not None:
                raise DataProtectionError(
                    "File is linked to a customer document; "
                    "request deletion of the document instead"
                )

        for child_type, ids in related:
            if self.repo.active_holds_for(child_type, ids):
                raise DataProtectionError(
                    "A related resource is protected by an active legal hold"
                )

    def _storage_paths_for_customer(self, customer_id: uuid.UUID) -> list[str]:
        _document_ids, _verification_ids, _compliance_ids, file_ids = self._related_ids(
            customer_id
        )
        if not file_ids:
            return []
        return list(
            self.db.scalars(
                select(File.storage_path).where(
                    File.tenant_id == self.tenant_id,
                    File.id.in_(file_ids),
                )
            ).all()
        )

    def _file_for_document(self, document: CustomerDocument) -> File | None:
        try:
            file_id = uuid.UUID(document.file_reference)
        except (ValueError, TypeError, AttributeError):
            return None
        return self.db.scalar(
            select(File).where(File.id == file_id, File.tenant_id == self.tenant_id)
        )

    def _delete_storage_for_resource(
        self, resource_type: str, resource_id: uuid.UUID
    ) -> None:
        if self.storage is None:
            raise DataProtectionError(
                "Storage provider is required to execute deletion"
            )
        paths: list[str] = []
        if resource_type == DataResourceType.FILE.value:
            file_row = self.db.scalar(
                select(File).where(
                    File.id == resource_id, File.tenant_id == self.tenant_id
                )
            )
            if file_row is None:
                return
            referenced = self.db.scalar(
                select(CustomerDocument.id)
                .where(
                    CustomerDocument.tenant_id == self.tenant_id,
                    CustomerDocument.file_reference == str(resource_id),
                )
                .limit(1)
            )
            if referenced is not None:
                raise DataProtectionError(
                    "File is linked to a customer document; delete the document instead"
                )
            paths = [file_row.storage_path]
        elif resource_type == DataResourceType.DOCUMENT.value:
            doc = self.db.scalar(
                select(CustomerDocument).where(
                    CustomerDocument.id == resource_id,
                    CustomerDocument.tenant_id == self.tenant_id,
                )
            )
            if doc:
                file_row = self._file_for_document(doc)
                if file_row:
                    paths = [file_row.storage_path]
        elif resource_type == DataResourceType.CUSTOMER.value:
            paths = self._storage_paths_for_customer(resource_id)
        elif resource_type == DataResourceType.VERIFICATION_CASE.value:
            docs = self.db.scalars(
                select(CustomerDocument).where(
                    CustomerDocument.tenant_id == self.tenant_id,
                    CustomerDocument.verification_case_id == resource_id,
                )
            ).all()
            for doc in docs:
                file_row = self._file_for_document(doc)
                if file_row:
                    paths.append(file_row.storage_path)
        for path in dict.fromkeys(paths):
            self.storage.delete(path)

    def _delete_database_resource(
        self, resource_type: str, resource_id: uuid.UUID
    ) -> None:
        """Delete a record and its FK-dependent records within the active tenant.

        This walks the ORM's loaded FK metadata so child tables that are not
        represented by a direct relationship (for example audit/history rows)
        cannot block erasure or accidentally retain related personal information.
        """
        table_by_type: dict[str, Table] = {
            DataResourceType.CUSTOMER: cast(Table, Customer.__table__),
            DataResourceType.DOCUMENT: cast(Table, CustomerDocument.__table__),
            DataResourceType.VERIFICATION_CASE: cast(
                Table, IdentityVerificationCase.__table__
            ),
            DataResourceType.COMPLIANCE_CASE: cast(Table, ComplianceCase.__table__),
            DataResourceType.FILE: cast(Table, File.__table__),
        }
        table = table_by_type[resource_type]
        conditions = [table.c.id == resource_id]
        if "tenant_id" in table.c:
            conditions.append(table.c.tenant_id == self.tenant_id)
        row = self.db.execute(select(table).where(*conditions)).mappings().first()
        if row is None:
            return

        # The older file association is stored as a UUID string in
        # customer_documents.file_reference, not an FK. Remove its metadata too.
        file_ids: list[uuid.UUID] = []
        if resource_type == DataResourceType.CUSTOMER.value:
            _document_ids, _verification_ids, _compliance_ids, file_ids = (
                self._related_ids(resource_id)
            )
        elif resource_type == DataResourceType.DOCUMENT.value:
            document = self.db.scalar(
                select(CustomerDocument).where(
                    CustomerDocument.id == resource_id,
                    CustomerDocument.tenant_id == self.tenant_id,
                )
            )
            file_row = (
                self._file_for_document(document) if document is not None else None
            )
            if file_row is not None:
                file_ids = [file_row.id]
        elif resource_type == DataResourceType.VERIFICATION_CASE.value:
            docs = self.db.scalars(
                select(CustomerDocument).where(
                    CustomerDocument.tenant_id == self.tenant_id,
                    CustomerDocument.verification_case_id == resource_id,
                )
            ).all()
            file_ids = [
                file_row.id
                for doc in docs
                if (file_row := self._file_for_document(doc)) is not None
            ]
        if file_ids:
            self.db.execute(
                delete(File).where(
                    File.id.in_(file_ids), File.tenant_id == self.tenant_id
                )
            )

        self._delete_fk_descendants(table, dict(row), set())
        self.db.execute(delete(table).where(*conditions))
        self.db.flush()

    def _delete_fk_descendants(
        self,
        parent_table: Table,
        parent_values: dict[str, Any],
        visited: set[tuple[str, tuple[Any, ...]]],
    ) -> None:
        primary_key = tuple(parent_table.primary_key.columns)
        primary_values = tuple(parent_values.get(column.key) for column in primary_key)
        identity = (parent_table.fullname, primary_values)
        if identity in visited:
            return
        visited.add(identity)

        for child_table in tuple(Base.metadata.tables.values()):
            if child_table is parent_table:
                continue
            foreign_key_columns = [
                column
                for column in child_table.columns
                if any(
                    foreign_key.column.table is parent_table
                    for foreign_key in column.foreign_keys
                )
            ]
            for child_column in foreign_key_columns:
                matching_foreign_keys = [
                    foreign_key
                    for foreign_key in child_column.foreign_keys
                    if foreign_key.column.table is parent_table
                ]
                for foreign_key in matching_foreign_keys:
                    parent_value = parent_values.get(foreign_key.column.key)
                    if parent_value is None:
                        continue
                    conditions = [child_column == parent_value]
                    if "tenant_id" in child_table.c:
                        conditions.append(child_table.c.tenant_id == self.tenant_id)
                    child_rows = (
                        self.db.execute(select(child_table).where(*conditions))
                        .mappings()
                        .all()
                    )
                    for child_row in child_rows:
                        self._delete_fk_descendants(
                            child_table, dict(child_row), visited
                        )
                    # Explicit tenant predicate is intentionally retained even though
                    # the central SQLAlchemy tenant guard applies its own predicate.
                    self.db.execute(delete(child_table).where(*conditions))
