"""Async partner-onboarding document upload path.

The larger PartnerOnboardingPortalService remains synchronous; this focused
service uses AsyncSession only for the upload endpoint.
"""

import hashlib
import hmac
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.models.partner_onboarding import (
    PartnerOnboarding,
    PartnerOnboardingDocument,
)
from app.repositories.async_partner_onboarding_repository import (
    AsyncPartnerOnboardingRepository,
)
from app.services.async_audit_service import AsyncAuditService
from app.utils.date_time import utc_now
from app.utils.enums import AuditEventType, PartnerOnboardingStatus
from app.utils.errors import bad_request, conflict, not_found, unauthorized

REQUIRED_DOCUMENT_TYPES = {"business_registration", "regulatory_license"}
ALLOWED_DOCUMENT_TYPES = REQUIRED_DOCUMENT_TYPES | {
    "tax_certificate",
    "authorized_signatory_list",
    "other",
}
_MUTABLE_STATUSES = {
    PartnerOnboardingStatus.REQUESTED,
    PartnerOnboardingStatus.BUSINESS_INFORMATION,
    PartnerOnboardingStatus.COMPLIANCE_REVIEW,
    PartnerOnboardingStatus.TECHNICAL_SETUP,
}
_DOCUMENT_EXTENSIONS = {
    "application/pdf": ".pdf",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "text/plain": ".txt",
}
PORTAL_TOKEN_TTL_DAYS = 30


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _write_private_document(
    *,
    storage_path: str,
    content: bytes,
) -> None:
    destination = Path(storage_path)
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        destination.parent.chmod(0o700)
    except OSError:
        pass
    with destination.open("xb") as handle:
        handle.write(content)
    destination.chmod(0o600)


class AsyncPartnerOnboardingDocumentService:
    """Async upload endpoint for public partner-onboarding documents."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repository = AsyncPartnerOnboardingRepository(db)
        self.audit_service = AsyncAuditService(db)

    async def _get_portal_request(
        self,
        onboarding_id: UUID,
        token: str,
    ) -> PartnerOnboarding:
        onboarding = await self.repository.get_by_id(
            onboarding_id,
            for_update=True,
        )
        if onboarding is None or not onboarding.portal_token_hash:
            raise not_found("Onboarding portal")
        supplied_hash = _hash_token(token)
        if not hmac.compare_digest(onboarding.portal_token_hash, supplied_hash):
            raise not_found("Onboarding portal")
        if (
            onboarding.portal_token_expires_at is None
            or onboarding.portal_token_expires_at <= utc_now()
        ):
            raise unauthorized("Onboarding portal token has expired.")
        if onboarding.status not in _MUTABLE_STATUSES:
            raise conflict("This onboarding request can no longer be changed.")
        return onboarding

    async def upload_document(
        self,
        *,
        onboarding_id: UUID,
        token: str,
        document_type: str,
        file: UploadFile,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> PartnerOnboardingDocument:
        onboarding = await self._get_portal_request(onboarding_id, token)
        if document_type not in ALLOWED_DOCUMENT_TYPES:
            raise bad_request(
                "Unsupported document_type. Use business_registration, "
                "regulatory_license, tax_certificate, authorized_signatory_list, "
                "or other."
            )
        if not file.filename:
            raise bad_request("A document filename is required.")

        content_type = file.content_type or ""
        if (
            content_type not in set(settings.ALLOWED_FILE_TYPES)
            or content_type not in _DOCUMENT_EXTENSIONS
        ):
            raise bad_request("This document content type is not supported.")

        content = await file.read(settings.MAX_FILE_SIZE + 1)
        if not content:
            raise bad_request("The uploaded document is empty.")
        if len(content) > settings.MAX_FILE_SIZE:
            raise bad_request("Document exceeds the configured maximum file size.")
        if content_type == "application/pdf" and not content.startswith(b"%PDF-"):
            raise bad_request("The uploaded file does not have a valid PDF signature.")
        if content_type == "image/png" and not content.startswith(b"\x89PNG\r\n\x1a\n"):
            raise bad_request("The uploaded file does not have a valid PNG signature.")
        if content_type == "image/jpeg" and not content.startswith(b"\xff\xd8\xff"):
            raise bad_request("The uploaded file does not have a valid JPEG signature.")

        original_filename = file.filename.replace("\\", "/").split("/")[-1].strip()
        original_filename = original_filename[:255]
        if not original_filename:
            raise bad_request("A valid document filename is required.")

        storage_root = Path(settings.STORAGE_PATH).expanduser().resolve()
        destination = (
            storage_root
            / "partner-onboarding"
            / str(onboarding.id)
            / f"{uuid4().hex}{_DOCUMENT_EXTENSIONS[content_type]}"
        )
        storage_path = str(destination)

        try:
            await run_in_threadpool(
                _write_private_document,
                storage_path=storage_path,
                content=content,
            )
            document = PartnerOnboardingDocument(
                onboarding_id=onboarding.id,
                document_type=document_type,
                original_filename=original_filename,
                storage_path=storage_path,
                content_type=content_type,
                file_size=len(content),
                sha256=hashlib.sha256(content).hexdigest(),
                review_status="PENDING_REVIEW",
            )
            await self.repository.create_document(document)
            await self.repository.add_history(
                onboarding=onboarding,
                action="DOCUMENT_SUBMITTED",
                previous_status=onboarding.status,
                changed_by=None,
                notes=f"Document submitted: {document_type}.",
            )
            await self.audit_service.log_event(
                event_type=AuditEventType.PARTNER_ONBOARDING_UPDATED,
                email=onboarding.contact_email,
                ip_address=ip_address,
                user_agent=user_agent,
                resource_type="partner_onboarding_document",
                resource_id=document.id,
            )
            await self.db.commit()
            await self.db.refresh(document)
            return document
        except Exception:
            await self.db.rollback()
            try:
                await run_in_threadpool(Path(storage_path).unlink, missing_ok=True)
            except Exception:
                pass
            raise
