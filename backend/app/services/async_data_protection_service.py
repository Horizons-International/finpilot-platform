"""Native-async database mutations for tenant-scoped data protection.

Physical deletion deliberately remains in ``DataProtectionService`` because it
coordinates database commits with external storage deletion.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.data_protection import DataProtectionError
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
from app.repositories.async_data_protection_read_repository import (
    AsyncDataProtectionReadRepository,
)


class AsyncDataProtectionService:
    """Perform policy, legal-hold and deletion-approval writes asynchronously.

    The service never commits: callers own the transaction boundary, which keeps
    the audit row and the business mutation atomic.
    """

    ALLOWED_RESOURCE_TYPES = {item.value for item in DataResourceType}

    def __init__(self, db: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.db = db
        self.tenant_id = tenant_id
        # Reuse the already-established tenant-context validation used by reads.
        self.repository = AsyncDataProtectionReadRepository(db, tenant_id)

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
        details: dict[str, Any] | None = None,
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

    async def set_policy(
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

        policy = await self.db.scalar(
            select(DataProtectionPolicy)
            .where(
                DataProtectionPolicy.tenant_id == self.tenant_id,
                DataProtectionPolicy.resource_type == resource_type,
            )
            .with_for_update()
        )
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
        await self.db.flush()
        self._audit(
            "RETENTION_POLICY_UPDATED",
            actor_id,
            resource_type,
            policy.id,
            {"retention_days": retention_days, "enabled": enabled},
        )
        await self.db.flush()
        return policy

    async def create_legal_hold(
        self,
        resource_type: str,
        resource_id: uuid.UUID,
        reason: str,
        actor_id: uuid.UUID,
    ) -> DataLegalHold:
        resource_type = self._validate_resource_type(resource_type)
        if not reason.strip():
            raise DataProtectionError("A legal-hold reason is required")
        if not await self._resource_exists(resource_type, resource_id):
            raise DataProtectionError("Resource not found in the current tenant")
        active = await self.db.scalar(
            select(DataLegalHold.id)
            .where(
                DataLegalHold.tenant_id == self.tenant_id,
                DataLegalHold.resource_type == resource_type,
                DataLegalHold.resource_id == resource_id,
                DataLegalHold.active.is_(True),
            )
            .limit(1)
        )
        if active is not None:
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
        await self.db.flush()
        self._audit(
            "LEGAL_HOLD_CREATED",
            actor_id,
            resource_type,
            resource_id,
            {"hold_id": str(hold.id)},
        )
        await self.db.flush()
        return hold

    async def release_legal_hold(
        self, hold_id: uuid.UUID, actor_id: uuid.UUID
    ) -> DataLegalHold:
        hold = await self.db.scalar(
            select(DataLegalHold)
            .where(
                DataLegalHold.id == hold_id,
                DataLegalHold.tenant_id == self.tenant_id,
                DataLegalHold.active.is_(True),
            )
            .with_for_update()
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
        await self.db.flush()
        return hold

    async def request_deletion(
        self,
        resource_type: str,
        resource_id: uuid.UUID,
        reason: str,
        actor_id: uuid.UUID,
    ) -> DataDeletionRequest:
        resource_type = self._validate_resource_type(resource_type)
        if not reason.strip():
            raise DataProtectionError("A deletion reason is required")
        if not await self._resource_exists(resource_type, resource_id):
            raise DataProtectionError("Resource not found in the current tenant")
        await self._assert_no_holds(resource_type, resource_id)
        request = DataDeletionRequest(
            tenant_id=self.tenant_id,
            resource_type=resource_type,
            resource_id=resource_id,
            status=DataDeletionStatus.REQUESTED,
            requested_by=actor_id,
            reason=reason.strip(),
        )
        self.db.add(request)
        await self.db.flush()
        self._audit(
            "DELETION_REQUESTED",
            actor_id,
            resource_type,
            resource_id,
            {"request_id": str(request.id)},
        )
        await self.db.flush()
        return request

    async def approve_deletion(
        self, request_id: uuid.UUID, actor_id: uuid.UUID
    ) -> DataDeletionRequest:
        request = await self.db.scalar(
            select(DataDeletionRequest)
            .where(
                DataDeletionRequest.id == request_id,
                DataDeletionRequest.tenant_id == self.tenant_id,
            )
            .with_for_update()
        )
        if request is None:
            raise DataProtectionError("Deletion request not found")
        if request.status != DataDeletionStatus.REQUESTED:
            raise DataProtectionError("Deletion request is not awaiting approval")
        if request.requested_by == actor_id:
            raise DataProtectionError(
                "A different administrator must approve the deletion request"
            )
        await self._assert_no_holds(request.resource_type, request.resource_id)
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
        await self.db.flush()
        return request

    async def _resource_exists(
        self, resource_type: str, resource_id: uuid.UUID
    ) -> bool:
        model_by_type: dict[str, Any] = {
            DataResourceType.CUSTOMER.value: Customer,
            DataResourceType.DOCUMENT.value: CustomerDocument,
            DataResourceType.VERIFICATION_CASE.value: IdentityVerificationCase,
            DataResourceType.COMPLIANCE_CASE.value: ComplianceCase,
            DataResourceType.FILE.value: File,
        }
        model = model_by_type[resource_type]
        result = await self.db.scalar(
            select(model.id).where(
                model.id == resource_id,
                model.tenant_id == self.tenant_id,
            )
        )
        return result is not None

    async def _active_hold_exists(
        self, resource_type: str, resource_ids: list[uuid.UUID]
    ) -> bool:
        if not resource_ids:
            return False
        result = await self.db.scalar(
            select(DataLegalHold.id)
            .where(
                DataLegalHold.tenant_id == self.tenant_id,
                DataLegalHold.resource_type == resource_type,
                DataLegalHold.resource_id.in_(resource_ids),
                DataLegalHold.active.is_(True),
            )
            .limit(1)
        )
        return result is not None

    async def _file_for_document(self, document: CustomerDocument) -> File | None:
        try:
            file_id = uuid.UUID(document.file_reference)
        except (ValueError, TypeError, AttributeError):
            return None
        return await self.db.scalar(
            select(File).where(
                File.id == file_id,
                File.tenant_id == self.tenant_id,
            )
        )

    async def _related_ids(
        self, customer_id: uuid.UUID
    ) -> tuple[list[uuid.UUID], list[uuid.UUID], list[uuid.UUID], list[uuid.UUID]]:
        documents_result = await self.db.scalars(
            select(CustomerDocument).where(
                CustomerDocument.tenant_id == self.tenant_id,
                CustomerDocument.customer_id == customer_id,
            )
        )
        documents = list(documents_result.all())
        verification_result = await self.db.scalars(
            select(IdentityVerificationCase.id).where(
                IdentityVerificationCase.tenant_id == self.tenant_id,
                IdentityVerificationCase.customer_id == customer_id,
            )
        )
        compliance_result = await self.db.scalars(
            select(ComplianceCase.id).where(
                ComplianceCase.tenant_id == self.tenant_id,
                ComplianceCase.customer_id == customer_id,
            )
        )
        file_ids: list[uuid.UUID] = []
        for document in documents:
            file_row = await self._file_for_document(document)
            if file_row is not None:
                file_ids.append(file_row.id)
        return (
            [row.id for row in documents],
            list(verification_result.all()),
            list(compliance_result.all()),
            file_ids,
        )

    async def _assert_no_holds(
        self, resource_type: str, resource_id: uuid.UUID
    ) -> None:
        if await self._active_hold_exists(resource_type, [resource_id]):
            raise DataProtectionError("Resource is protected by an active legal hold")

        related: list[tuple[str, list[uuid.UUID]]] = []
        if resource_type == DataResourceType.CUSTOMER.value:
            (
                document_ids,
                verification_ids,
                compliance_ids,
                file_ids,
            ) = await self._related_ids(resource_id)
            related.extend(
                [
                    ("DOCUMENT", document_ids),
                    ("VERIFICATION_CASE", verification_ids),
                    ("COMPLIANCE_CASE", compliance_ids),
                    ("FILE", file_ids),
                ]
            )
        elif resource_type == DataResourceType.DOCUMENT.value:
            document = await self.db.scalar(
                select(CustomerDocument).where(
                    CustomerDocument.id == resource_id,
                    CustomerDocument.tenant_id == self.tenant_id,
                )
            )
            if document is not None:
                related.append(("CUSTOMER", [document.customer_id]))
                if document.verification_case_id is not None:
                    related.append(
                        ("VERIFICATION_CASE", [document.verification_case_id])
                    )
                file_row = await self._file_for_document(document)
                if file_row is not None:
                    related.append(("FILE", [file_row.id]))
        elif resource_type == DataResourceType.VERIFICATION_CASE.value:
            case = await self.db.scalar(
                select(IdentityVerificationCase).where(
                    IdentityVerificationCase.id == resource_id,
                    IdentityVerificationCase.tenant_id == self.tenant_id,
                )
            )
            if case is not None:
                related.append(("CUSTOMER", [case.customer_id]))
                docs_result = await self.db.scalars(
                    select(CustomerDocument).where(
                        CustomerDocument.tenant_id == self.tenant_id,
                        CustomerDocument.verification_case_id == resource_id,
                    )
                )
                docs = list(docs_result.all())
                file_ids = []
                for document in docs:
                    file_row = await self._file_for_document(document)
                    if file_row is not None:
                        file_ids.append(file_row.id)
                related.extend(
                    [("DOCUMENT", [doc.id for doc in docs]), ("FILE", file_ids)]
                )
        elif resource_type == DataResourceType.COMPLIANCE_CASE.value:
            case = await self.db.scalar(
                select(ComplianceCase).where(
                    ComplianceCase.id == resource_id,
                    ComplianceCase.tenant_id == self.tenant_id,
                )
            )
            if case is not None:
                related.append(("CUSTOMER", [case.customer_id]))
        elif resource_type == DataResourceType.FILE.value:
            referenced = await self.db.scalar(
                select(CustomerDocument.id)
                .where(
                    CustomerDocument.tenant_id == self.tenant_id,
                    CustomerDocument.file_reference == str(resource_id),
                )
                .limit(1)
            )
            if referenced is not None:
                raise DataProtectionError(
                    "File is linked to a customer document; "
                    "request deletion of the document instead"
                )

        for child_type, ids in related:
            if await self._active_hold_exists(child_type, ids):
                raise DataProtectionError(
                    "A related resource is protected by an active legal hold"
                )
