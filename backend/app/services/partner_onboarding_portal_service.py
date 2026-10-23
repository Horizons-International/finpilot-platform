"""Self-service onboarding portal and controlled tenant activation."""

import hashlib
import hmac
import secrets
from datetime import timedelta
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.api_key import APIKey
from app.models.organization import Organization
from app.models.partner_onboarding import (
    PartnerOnboarding,
    PartnerOnboardingAdministrator,
    PartnerOnboardingDocument,
)
from app.models.tenant import Tenant
from app.models.user_invitation import UserInvitation
from app.repositories.partner_onboarding_repository import PartnerOnboardingRepository
from app.schemas.partner_onboarding import (
    PartnerBusinessInformationUpdate,
    PartnerOnboardingAdministratorCreate,
    PartnerOnboardingAdministratorResponse,
    PartnerOnboardingCreate,
    PartnerOnboardingDocumentResponse,
    PartnerOnboardingProgressResponse,
    PartnerOnboardingProgressStep,
    PartnerTechnicalSetupUpdate,
)
from app.services.audit_service import AuditService
from app.services.partner_onboarding_service import PartnerOnboardingService
from app.utils.date_time import utc_now
from app.utils.enums import (
    APIKeyStatus,
    AuditEventType,
    OrganizationStatus,
    PartnerOnboardingStatus,
    TenantStatus,
    UserRole,
)
from app.utils.errors import bad_request, conflict, not_found, unauthorized

PORTAL_TOKEN_TTL_DAYS = 30
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


class PartnerOnboardingPortalService:
    """Portal functionality for prospective enterprises before tenant creation.

    The customer-facing portal uses a high-entropy bearer token. Only a SHA-256
    hash is persisted. Platform staff still use the existing platform-admin
    protected partner-onboarding routes for assignment, evidence review and
    workflow approval.
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = PartnerOnboardingRepository(db)
        self.audit_service = AuditService(db)

    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def create_portal_request(
        self,
        data: PartnerOnboardingCreate,
        *,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[PartnerOnboarding, str]:
        email = str(data.contact_email).strip().lower()
        if self.repository.has_open_request_for_email(email):
            raise conflict(
                "An open partner onboarding request already exists for this contact "
                "email."
            )

        raw_token = secrets.token_urlsafe(32)
        token_expires_at = utc_now() + timedelta(days=PORTAL_TOKEN_TTL_DAYS)
        onboarding = PartnerOnboarding(
            organization_name=data.organization_name.strip(),
            legal_name=data.legal_name,
            registration_number=data.registration_number,
            tax_identification_number=data.tax_identification_number,
            industry=data.industry,
            business_description=data.business_description,
            contact_name=data.contact_name.strip(),
            contact_email=email,
            contact_phone=data.contact_phone,
            website=data.website,
            country=data.country,
            status=PartnerOnboardingStatus.REQUESTED,
            portal_token_hash=self._hash_token(raw_token),
            portal_token_expires_at=token_expires_at,
        )
        try:
            self.repository.create(onboarding)
            self.repository.add_history(
                onboarding=onboarding,
                action="PORTAL_REQUESTED",
                previous_status=None,
                changed_by=None,
                notes="Self-service partner onboarding portal created.",
            )
            self.audit_service.log_event(
                event_type=AuditEventType.PARTNER_ONBOARDING_CREATED,
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
                resource_type="partner_onboarding",
                resource_id=onboarding.id,
            )
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            constraint = getattr(
                getattr(exc.orig, "diag", None), "constraint_name", None
            )
            if constraint in {
                "uq_partner_onboarding_non_rejected_contact_email",
                "uq_partner_onboarding_portal_token_hash",
            }:
                raise conflict(
                    "An open onboarding request already exists for this contact email."
                ) from exc
            raise
        self.db.refresh(onboarding)
        return onboarding, raw_token

    def _get_portal_request(
        self,
        onboarding_id: UUID,
        token: str,
        *,
        for_update: bool = False,
    ) -> PartnerOnboarding:
        onboarding = self.repository.get_by_id(onboarding_id, for_update=for_update)
        # Avoid revealing whether an onboarding ID exists to a caller without a token.
        if onboarding is None or not onboarding.portal_token_hash:
            raise not_found("Onboarding portal")
        supplied_hash = self._hash_token(token)
        if not hmac.compare_digest(onboarding.portal_token_hash, supplied_hash):
            raise not_found("Onboarding portal")
        if (
            onboarding.portal_token_expires_at is None
            or onboarding.portal_token_expires_at <= utc_now()
        ):
            raise unauthorized("Onboarding portal token has expired.")
        return onboarding

    @staticmethod
    def _ensure_mutable(onboarding: PartnerOnboarding) -> None:
        if onboarding.status not in _MUTABLE_STATUSES:
            raise conflict("This onboarding request can no longer be changed.")

    @staticmethod
    def _business_information_complete(onboarding: PartnerOnboarding) -> bool:
        required = (
            onboarding.organization_name,
            onboarding.legal_name,
            onboarding.registration_number,
            onboarding.tax_identification_number,
            onboarding.industry,
            onboarding.contact_name,
            onboarding.contact_email,
            onboarding.country,
        )
        return all(isinstance(value, str) and bool(value.strip()) for value in required)

    @staticmethod
    def _latest_documents(
        onboarding: PartnerOnboarding,
    ) -> dict[str, PartnerOnboardingDocument]:
        latest: dict[str, PartnerOnboardingDocument] = {}
        for document in sorted(
            onboarding.documents,
            key=lambda item: (item.created_at, str(item.id)),
        ):
            latest[document.document_type] = document
        return latest

    def _required_documents_submitted(self, onboarding: PartnerOnboarding) -> bool:
        latest = self._latest_documents(onboarding)
        return all(
            document_type in latest
            and latest[document_type].review_status != "REJECTED"
            for document_type in REQUIRED_DOCUMENT_TYPES
        )

    def _required_documents_approved(self, onboarding: PartnerOnboarding) -> bool:
        latest = self._latest_documents(onboarding)
        return all(
            document_type in latest
            and latest[document_type].review_status == "APPROVED"
            for document_type in REQUIRED_DOCUMENT_TYPES
        )

    def _admin_emails_are_available(self, onboarding: PartnerOnboarding) -> None:
        for administrator in onboarding.administrators:
            existing = self.repository.get_existing_user_id_by_email(
                administrator.email
            )
            if existing is not None:
                raise conflict(
                    f"Administrator email {administrator.email} already belongs "
                    "to a FinPilot user."
                )

    def update_business_information(
        self,
        *,
        onboarding_id: UUID,
        token: str,
        data: PartnerBusinessInformationUpdate,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> PartnerOnboarding:
        onboarding = self._get_portal_request(onboarding_id, token, for_update=True)
        self._ensure_mutable(onboarding)
        if onboarding.status not in {
            PartnerOnboardingStatus.REQUESTED,
            PartnerOnboardingStatus.BUSINESS_INFORMATION,
        }:
            raise conflict(
                "Business information can only be changed before compliance review."
            )
        values = data.model_dump(exclude_unset=True)
        if not values:
            raise bad_request("No business information fields were provided.")
        if values.get("contact_email") is not None:
            email = str(values["contact_email"]).strip().lower()
            if self.repository.has_open_request_for_email(
                email, exclude_id=onboarding.id
            ):
                raise conflict(
                    "An open onboarding request already exists for this contact email."
                )
            values["contact_email"] = email
        for field, value in values.items():
            if value is None:
                continue
            if field == "contact_email":
                value = str(value).strip().lower()
            elif isinstance(value, str):
                value = value.strip()
            setattr(onboarding, field, value)
        onboarding.updated_at = utc_now()
        self.repository.add_history(
            onboarding=onboarding,
            action="BUSINESS_INFORMATION_UPDATED",
            previous_status=onboarding.status,
            changed_by=None,
            notes="Business information updated by the authenticated portal token.",
        )
        self.audit_service.log_event(
            event_type=AuditEventType.PARTNER_ONBOARDING_UPDATED,
            email=onboarding.contact_email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="partner_onboarding",
            resource_id=onboarding.id,
        )
        self.db.commit()
        self.db.refresh(onboarding)
        return onboarding

    def add_administrator(
        self,
        *,
        onboarding_id: UUID,
        token: str,
        data: PartnerOnboardingAdministratorCreate,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[PartnerOnboardingAdministrator, str]:
        onboarding = self._get_portal_request(onboarding_id, token, for_update=True)
        self._ensure_mutable(onboarding)
        email = str(data.email).strip().lower()
        if self.repository.get_existing_user_id_by_email(email) is not None:
            raise conflict(
                "This email already belongs to a FinPilot user. Nominate a different "
                "administrator email."
            )
        if any(item.email.lower() == email for item in onboarding.administrators):
            raise conflict("This administrator has already been added to onboarding.")
        raw_invitation_token = secrets.token_urlsafe(32)
        administrator = PartnerOnboardingAdministrator(
            onboarding_id=onboarding.id,
            first_name=data.first_name.strip(),
            last_name=data.last_name.strip(),
            email=email,
            role=UserRole.ADMINISTRATOR.value,
            department=data.department,
            invitation_token_hash=self._hash_token(raw_invitation_token),
            status="PENDING",
        )
        try:
            self.repository.create_administrator(administrator)
            self.repository.add_history(
                onboarding=onboarding,
                action="ADMINISTRATOR_NOMINATED",
                previous_status=onboarding.status,
                changed_by=None,
                notes=f"Administrator nomination recorded for {email}.",
            )
            self.audit_service.log_event(
                event_type=AuditEventType.PARTNER_ONBOARDING_UPDATED,
                email=onboarding.contact_email,
                ip_address=ip_address,
                user_agent=user_agent,
                resource_type="partner_onboarding",
                resource_id=onboarding.id,
            )
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise conflict("This administrator has already been added.") from exc
        self.db.refresh(administrator)
        return administrator, raw_invitation_token

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
        onboarding = self._get_portal_request(onboarding_id, token, for_update=True)
        self._ensure_mutable(onboarding)
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
        destination_dir = storage_root / "partner-onboarding" / str(onboarding.id)
        destination_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            destination_dir.chmod(0o700)
        except OSError:
            pass
        destination = destination_dir / (
            f"{uuid4().hex}{_DOCUMENT_EXTENSIONS[content_type]}"
        )
        try:
            with destination.open("xb") as handle:
                handle.write(content)
            destination.chmod(0o600)
            document = PartnerOnboardingDocument(
                onboarding_id=onboarding.id,
                document_type=document_type,
                original_filename=original_filename,
                storage_path=str(destination),
                content_type=content_type,
                file_size=len(content),
                sha256=hashlib.sha256(content).hexdigest(),
                review_status="PENDING_REVIEW",
            )
            self.repository.create_document(document)
            self.repository.add_history(
                onboarding=onboarding,
                action="DOCUMENT_SUBMITTED",
                previous_status=onboarding.status,
                changed_by=None,
                notes=f"Document submitted: {document_type}.",
            )
            self.audit_service.log_event(
                event_type=AuditEventType.PARTNER_ONBOARDING_UPDATED,
                email=onboarding.contact_email,
                ip_address=ip_address,
                user_agent=user_agent,
                resource_type="partner_onboarding_document",
                resource_id=document.id,
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
            destination.unlink(missing_ok=True)
            raise
        self.db.refresh(document)
        return document

    def save_technical_setup(
        self,
        *,
        onboarding_id: UUID,
        token: str,
        data: PartnerTechnicalSetupUpdate,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> PartnerOnboarding:
        onboarding = self._get_portal_request(onboarding_id, token, for_update=True)
        self._ensure_mutable(onboarding)
        if onboarding.status == PartnerOnboardingStatus.API_CREDENTIALS:
            raise conflict("Technical setup can no longer be changed at this stage.")
        onboarding.technical_setup = data.model_dump(mode="json")
        onboarding.technical_setup_completed_at = utc_now()
        onboarding.updated_at = utc_now()
        self.repository.add_history(
            onboarding=onboarding,
            action="TECHNICAL_SETUP_COMPLETED",
            previous_status=onboarding.status,
            changed_by=None,
            notes="Customer technical setup details submitted.",
        )
        self.audit_service.log_event(
            event_type=AuditEventType.PARTNER_ONBOARDING_UPDATED,
            email=onboarding.contact_email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="partner_onboarding",
            resource_id=onboarding.id,
        )
        self.db.commit()
        self.db.refresh(onboarding)
        return onboarding

    def submit_for_review(
        self,
        *,
        onboarding_id: UUID,
        token: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> PartnerOnboarding:
        onboarding = self._get_portal_request(onboarding_id, token, for_update=True)
        if onboarding.status != PartnerOnboardingStatus.REQUESTED:
            raise conflict("Only a newly created onboarding request can be submitted.")
        if not self._business_information_complete(onboarding):
            raise conflict(
                "Complete all required business information before submission."
            )
        if not onboarding.administrators:
            raise conflict(
                "Add at least one organization administrator before submission."
            )
        if not self._required_documents_submitted(onboarding):
            raise conflict(
                "Upload the required business_registration and regulatory_license "
                "documents before submission."
            )
        previous_status = onboarding.status
        onboarding.status = PartnerOnboardingStatus.BUSINESS_INFORMATION
        onboarding.updated_at = utc_now()
        self.repository.add_history(
            onboarding=onboarding,
            action="SUBMITTED_FOR_REVIEW",
            previous_status=previous_status,
            changed_by=None,
            notes="Portal submission passed required-step validation.",
        )
        self.audit_service.log_event(
            event_type=AuditEventType.PARTNER_ONBOARDING_UPDATED,
            email=onboarding.contact_email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="partner_onboarding",
            resource_id=onboarding.id,
        )
        self.db.commit()
        self.db.refresh(onboarding)
        return onboarding

    def get_portal_progress(
        self, onboarding_id: UUID, *, token: str
    ) -> PartnerOnboardingProgressResponse:
        onboarding = self._get_portal_request(onboarding_id, token)
        return self._build_progress(onboarding)

    def get_internal_progress(
        self, onboarding_id: UUID
    ) -> PartnerOnboardingProgressResponse:
        onboarding = self.repository.get_by_id(onboarding_id)
        if onboarding is None:
            raise not_found("Partner onboarding request")
        return self._build_progress(onboarding)

    def _build_progress(
        self, onboarding: PartnerOnboarding
    ) -> PartnerOnboardingProgressResponse:
        business_complete = self._business_information_complete(onboarding)
        administrators_complete = len(onboarding.administrators) > 0
        documents_complete = self._required_documents_submitted(onboarding)
        technical_complete = (
            onboarding.technical_setup_completed_at is not None
            and bool(onboarding.technical_setup)
        )
        activated = onboarding.status == PartnerOnboardingStatus.ACTIVE
        latest = self._latest_documents(onboarding)
        approved = all(
            doc_type in latest and latest[doc_type].review_status == "APPROVED"
            for doc_type in REQUIRED_DOCUMENT_TYPES
        )
        step_data = [
            (
                "business_information",
                "Business information",
                business_complete,
                (
                    "Required legal entity and contact details are complete."
                    if business_complete
                    else (
                        "Provide the legal name, registration/tax numbers, industry "
                        "and contact details."
                    )
                ),
            ),
            (
                "administrators",
                "Add administrators",
                administrators_complete,
                (
                    f"{len(onboarding.administrators)} administrator(s) nominated."
                    if administrators_complete
                    else "Nominate at least one organization administrator."
                ),
            ),
            (
                "documents",
                "Submit required documents",
                documents_complete,
                (
                    "Required documents are submitted; internal approval is pending."
                    if documents_complete and not approved
                    else (
                        (
                            "Required business registration and regulatory license "
                            "documents are approved."
                        )
                        if approved
                        else (
                            "Upload business_registration and "
                            "regulatory_license documents."
                        )
                    )
                ),
            ),
            (
                "technical_setup",
                "Complete technical setup",
                technical_complete,
                (
                    "Technical setup details are saved."
                    if technical_complete
                    else (
                        "Provide the target environment, HTTPS callback URL and "
                        "integration contact."
                    )
                ),
            ),
            (
                "credentials",
                "Generate access credentials",
                activated,
                (
                    "The initial API key and administrator invitations were generated."
                    if activated
                    else (
                        "Credentials are issued only with "
                        "the approved account activation."
                    )
                ),
            ),
            (
                "activation",
                "Review and activation",
                activated,
                (
                    "The organization tenant has been activated."
                    if activated
                    else "Internal review and approval are not complete."
                ),
            ),
        ]
        steps = [
            PartnerOnboardingProgressStep(
                key=key, label=label, complete=complete, detail=detail
            )
            for key, label, complete, detail in step_data
        ]
        progress_percent = round(
            100 * sum(step.complete for step in steps) / len(steps)
        )
        return PartnerOnboardingProgressResponse(
            onboarding_id=onboarding.id,
            status=onboarding.status,
            progress_percent=progress_percent,
            steps=steps,
            documents=[
                PartnerOnboardingDocumentResponse.model_validate(item)
                for item in sorted(
                    onboarding.documents,
                    key=lambda row: (row.created_at, str(row.id)),
                    reverse=True,
                )
            ],
            administrators=[
                PartnerOnboardingAdministratorResponse.model_validate(administrator)
                for administrator in onboarding.administrators
            ],
            technical_setup=onboarding.technical_setup,
            created_at=onboarding.created_at,
            updated_at=onboarding.updated_at,
        )

    def ensure_can_advance(self, onboarding_id: UUID) -> None:
        """Enforce required steps for self-service portal submissions.

        Legacy/platform-created requests without a portal token retain their prior
        workflow behavior. Portal-created requests must satisfy the relevant step
        gate before staff can move the workflow forward.
        """
        onboarding = self.repository.get_by_id(onboarding_id)
        if onboarding is None:
            raise not_found("Partner onboarding request")
        if not onboarding.portal_token_hash:
            return
        if onboarding.status == PartnerOnboardingStatus.REQUESTED:
            raise conflict(
                "The customer must submit business information, administrators, "
                "and required documents through the portal before review can begin."
            )
        if onboarding.status == PartnerOnboardingStatus.BUSINESS_INFORMATION:
            if not self._business_information_complete(onboarding):
                raise conflict("Required business information is incomplete.")
            if not onboarding.administrators:
                raise conflict("At least one organization administrator is required.")
            if not self._required_documents_submitted(onboarding):
                raise conflict("Required business onboarding documents are missing.")
        elif onboarding.status == PartnerOnboardingStatus.COMPLIANCE_REVIEW:
            if not self._required_documents_approved(onboarding):
                raise conflict(
                    "Approve the required business_registration and regulatory_license "
                    "documents before moving to technical setup."
                )
        elif onboarding.status == PartnerOnboardingStatus.TECHNICAL_SETUP:
            if (
                not onboarding.technical_setup_completed_at
                or not onboarding.technical_setup
            ):
                raise conflict("Customer technical setup is not complete.")
            if not onboarding.administrators:
                raise conflict("At least one organization administrator is required.")
            self._admin_emails_are_available(onboarding)

    def review_document(
        self,
        *,
        onboarding_id: UUID,
        document_id: UUID,
        review_status: str,
        notes: str | None,
        actor_id: UUID,
        actor_email: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> PartnerOnboardingDocument:
        onboarding = self.repository.get_by_id(onboarding_id, for_update=True)
        if onboarding is None:
            raise not_found("Partner onboarding request")
        if onboarding.status != PartnerOnboardingStatus.COMPLIANCE_REVIEW:
            raise conflict("Documents can only be reviewed during compliance review.")
        document = self.repository.get_document(onboarding_id, document_id)
        if document is None:
            raise not_found("Partner onboarding document")
        document.review_status = review_status
        document.review_notes = notes
        document.reviewed_by = actor_id
        document.reviewed_at = utc_now()
        onboarding.updated_at = utc_now()
        self.repository.add_history(
            onboarding=onboarding,
            action="DOCUMENT_REVIEWED",
            previous_status=onboarding.status,
            changed_by=actor_id,
            notes=f"{document.document_type}: {review_status}. {notes or ''}".strip(),
        )
        self.audit_service.log_event(
            event_type=AuditEventType.PARTNER_ONBOARDING_UPDATED,
            user_id=actor_id,
            email=actor_email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="partner_onboarding_document",
            resource_id=document.id,
        )
        self.db.commit()
        self.db.refresh(document)
        return document

    def document_storage_path(
        self, onboarding_id: UUID, document_id: UUID
    ) -> tuple[Path, PartnerOnboardingDocument]:
        onboarding = self.repository.get_by_id(onboarding_id)
        if onboarding is None:
            raise not_found("Partner onboarding request")
        document = self.repository.get_document(onboarding_id, document_id)
        if document is None:
            raise not_found("Partner onboarding document")
        root = (
            Path(settings.STORAGE_PATH).expanduser().resolve()
            / "partner-onboarding"
            / str(onboarding_id)
        ).resolve()
        candidate = Path(document.storage_path).resolve()
        if root not in candidate.parents or not candidate.is_file():
            raise not_found("Stored onboarding document")
        return candidate, document

    def activate_and_issue_credentials(
        self,
        *,
        onboarding_id: UUID,
        actor_id: UUID,
        actor_email: str,
        ip_address: str | None,
        user_agent: str | None,
        notes: str | None,
    ) -> tuple[PartnerOnboarding, str]:
        """Atomically activate a portal-backed bank and issue initial credentials."""
        onboarding = self.repository.get_by_id(onboarding_id, for_update=True)
        if onboarding is None:
            raise not_found("Partner onboarding request")
        if onboarding.status in {
            PartnerOnboardingStatus.ACTIVE,
            PartnerOnboardingStatus.REJECTED,
        }:
            raise conflict("This onboarding request is already in a terminal state.")
        if onboarding.status != PartnerOnboardingStatus.API_CREDENTIALS:
            raise conflict(
                "Complete business information, compliance review, and technical "
                "setup before activation."
            )
        PartnerOnboardingService._require_assignee(onboarding)
        if not self._business_information_complete(onboarding):
            raise conflict("Required business information is incomplete.")
        if not onboarding.administrators:
            raise conflict("At least one organization administrator is required.")
        if not self._required_documents_approved(onboarding):
            raise conflict("All required onboarding documents must be approved.")
        if (
            not onboarding.technical_setup_completed_at
            or not onboarding.technical_setup
        ):
            raise conflict("Customer technical setup is not complete.")
        self._admin_emails_are_available(onboarding)

        slug = "".join(
            character if character.isascii() and character.isalnum() else "-"
            for character in onboarding.organization_name.upper()
        ).strip("-")
        while "--" in slug:
            slug = slug.replace("--", "-")
        tenant = Tenant(
            name=onboarding.organization_name,
            code=f"{(slug or 'PARTNER')[:38]}-{uuid4().hex[:8].upper()}",
            status=TenantStatus.ACTIVE,
        )
        raw_api_key = f"fp_live_{secrets.token_urlsafe(32)}"
        now = utc_now()
        original_tenant_context = self.db.info.get("tenant_id")
        had_tenant_context = "tenant_id" in self.db.info

        try:
            self.repository.create_tenant(tenant)
            # Tenant-owned rows must be created while the ORM tenant guard is bound
            # to the new tenant. The context is restored before platform-level audit.
            self.db.info["tenant_id"] = tenant.id
            organization = Organization(
                tenant_id=tenant.id,
                name=onboarding.organization_name,
                legal_name=onboarding.legal_name,
                registration_number=onboarding.registration_number,
                tax_identification_number=onboarding.tax_identification_number,
                industry=onboarding.industry,
                business_description=onboarding.business_description,
                contact_name=onboarding.contact_name,
                contact_email=onboarding.contact_email,
                contact_phone=onboarding.contact_phone,
                website=onboarding.website,
                country=onboarding.country,
                status=OrganizationStatus.ACTIVE,
                settings={},
            )
            self.repository.create_organization(organization)
            for administrator in onboarding.administrators:
                invitation = UserInvitation(
                    tenant_id=tenant.id,
                    email=administrator.email,
                    first_name=administrator.first_name,
                    last_name=administrator.last_name,
                    role=administrator.role,
                    department=administrator.department,
                    token_hash=administrator.invitation_token_hash,
                    expires_at=now
                    + timedelta(hours=settings.USER_INVITATION_EXPIRE_HOURS),
                    invited_by=actor_id,
                )
                self.repository.create_invitation(invitation)
                administrator.status = "INVITED"
                administrator.invited_at = now
            api_key = APIKey(
                tenant_id=tenant.id,
                name="Initial onboarding API key",
                key_hash=hashlib.sha256(raw_api_key.encode("utf-8")).hexdigest(),
                permissions=["customers:read", "customers:create"],
                status=APIKeyStatus.ACTIVE,
                created_by=None,
                created_at=now,
            )
            self.repository.create_api_key(api_key)
        except Exception:
            self.db.rollback()
            raise
        finally:
            if had_tenant_context:
                self.db.info["tenant_id"] = original_tenant_context
            else:
                self.db.info.pop("tenant_id", None)

        previous_status = onboarding.status
        onboarding.status = PartnerOnboardingStatus.ACTIVE
        onboarding.activated_tenant_id = tenant.id
        onboarding.activated_at = now
        onboarding.reviewed_at = onboarding.reviewed_at or now
        onboarding.updated_at = now
        self.repository.add_history(
            onboarding=onboarding,
            action="CREDENTIALS_GENERATED",
            previous_status=previous_status,
            changed_by=actor_id,
            notes="Initial API credential and administrator invitations were created.",
        )
        self.repository.add_history(
            onboarding=onboarding,
            action="APPROVED_AND_ACTIVATED",
            previous_status=previous_status,
            changed_by=actor_id,
            notes=notes or "Partner approved; tenant and organization activated.",
        )
        # Associate activation/credential audit entries with the tenant just
        # provisioned, then restore the platform request's original session scope.
        self.db.info["tenant_id"] = tenant.id
        try:
            self.audit_service.log_event(
                event_type=AuditEventType.PARTNER_ONBOARDING_APPROVED,
                user_id=actor_id,
                email=actor_email,
                ip_address=ip_address,
                user_agent=user_agent,
                resource_type="partner_onboarding",
                resource_id=onboarding.id,
            )
            self.audit_service.log_event(
                event_type=AuditEventType.API_KEY_CREATED,
                user_id=actor_id,
                email=actor_email,
                ip_address=ip_address,
                user_agent=user_agent,
                resource_type="api_key",
                resource_id=api_key.id,
            )
        finally:
            if had_tenant_context:
                self.db.info["tenant_id"] = original_tenant_context
            else:
                self.db.info.pop("tenant_id", None)
        self.db.commit()
        self.db.refresh(onboarding)
        return onboarding, raw_api_key
