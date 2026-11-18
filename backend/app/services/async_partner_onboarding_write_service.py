"""Native-async database writes for partner onboarding and its customer portal.

The separate document upload service continues to own the filesystem operation.
The synchronous document-download handler also remains synchronous because it
reads a local file. Every method here uses the caller's AsyncSession and leaves
commit/rollback ownership explicit at the service-method boundary, matching the
existing onboarding service contract.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from datetime import timedelta
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

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
from app.repositories.async_partner_onboarding_repository import (
    AsyncPartnerOnboardingRepository,
)
from app.schemas.partner_onboarding import (
    PartnerBusinessInformationUpdate,
    PartnerOnboardingAdministratorCreate,
    PartnerOnboardingCreate,
    PartnerTechnicalSetupUpdate,
)
from app.services.async_audit_service import AsyncAuditService
from app.utils.date_time import utc_now
from app.utils.enums import (
    APIKeyStatus,
    AuditEventType,
    OrganizationStatus,
    PartnerOnboardingStatus,
    TenantStatus,
    UserRole,
    UserStatus,
)
from app.utils.errors import bad_request, conflict, not_found, unauthorized

PORTAL_TOKEN_TTL_DAYS = 30
REQUIRED_DOCUMENT_TYPES = {"business_registration", "regulatory_license"}
_MUTABLE_STATUSES = {
    PartnerOnboardingStatus.REQUESTED,
    PartnerOnboardingStatus.BUSINESS_INFORMATION,
    PartnerOnboardingStatus.COMPLIANCE_REVIEW,
    PartnerOnboardingStatus.TECHNICAL_SETUP,
}
_TERMINAL_STATUSES = {
    PartnerOnboardingStatus.ACTIVE,
    PartnerOnboardingStatus.REJECTED,
}
_NEXT_STAGE = {
    PartnerOnboardingStatus.REQUESTED: PartnerOnboardingStatus.BUSINESS_INFORMATION,
    PartnerOnboardingStatus.BUSINESS_INFORMATION: (
        PartnerOnboardingStatus.COMPLIANCE_REVIEW
    ),
    PartnerOnboardingStatus.COMPLIANCE_REVIEW: PartnerOnboardingStatus.TECHNICAL_SETUP,
    PartnerOnboardingStatus.TECHNICAL_SETUP: PartnerOnboardingStatus.API_CREDENTIALS,
}


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class AsyncPartnerOnboardingWriteService:
    """Platform-side onboarding operations backed exclusively by AsyncSession."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repository = AsyncPartnerOnboardingRepository(db)
        self.audit = AsyncAuditService(db)

    async def _audit_event(
        self,
        event_type: AuditEventType,
        onboarding: PartnerOnboarding,
        *,
        actor_id: UUID | None = None,
        actor_email: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        resource_type: str = "partner_onboarding",
        resource_id: UUID | None = None,
    ) -> None:
        await self.audit.log_event(
            event_type=event_type,
            user_id=actor_id,
            email=actor_email or onboarding.contact_email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type=resource_type,
            resource_id=resource_id or onboarding.id,
        )

    async def create_request(self, data: PartnerOnboardingCreate) -> PartnerOnboarding:
        email = str(data.contact_email).strip().lower()
        if await self.repository.has_open_request_for_email(email):
            raise conflict(
                "An open partner onboarding request already exists for this contact "
                "email."
            )
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
        )
        try:
            await self.repository.create(onboarding)
            await self.repository.add_history(
                onboarding=onboarding,
                action="REQUESTED",
                previous_status=None,
                changed_by=None,
                notes="Partner onboarding request submitted.",
            )
            await self._audit_event(
                AuditEventType.PARTNER_ONBOARDING_CREATED, onboarding
            )
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            constraint_name = getattr(
                getattr(exc.orig, "diag", None), "constraint_name", None
            )
            if constraint_name == "uq_partner_onboarding_non_rejected_contact_email":
                raise conflict(
                    "An open partner onboarding request already exists for this "
                    "contact email."
                ) from exc
            raise
        await self.db.refresh(onboarding)
        return onboarding

    async def get_request(self, onboarding_id: UUID) -> PartnerOnboarding:
        onboarding = await self.repository.get_by_id(onboarding_id)
        if onboarding is None:
            raise not_found("Partner onboarding request")
        return onboarding

    async def _get_mutable_request(
        self, onboarding_id: UUID, *, for_update: bool = False
    ) -> PartnerOnboarding:
        onboarding = await self.repository.get_by_id(
            onboarding_id, for_update=for_update
        )
        if onboarding is None:
            raise not_found("Partner onboarding request")
        if onboarding.status in _TERMINAL_STATUSES:
            raise conflict("This onboarding request is already in a terminal state.")
        return onboarding

    async def assign_reviewer(
        self,
        *,
        onboarding_id: UUID,
        assigned_to: UUID,
        actor_id: UUID,
        actor_email: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> PartnerOnboarding:
        onboarding = await self._get_mutable_request(onboarding_id, for_update=True)
        reviewer = await self.repository.get_platform_admin(assigned_to)
        if reviewer is None or not reviewer.is_platform_admin:
            raise bad_request(
                "The assigned reviewer must be an active platform administrator."
            )
        if reviewer.status != UserStatus.ACTIVE or reviewer.is_deleted:
            raise bad_request("The assigned reviewer must be active.")
        onboarding.assigned_to = reviewer.id
        onboarding.updated_at = utc_now()
        await self.repository.add_history(
            onboarding=onboarding,
            action="ASSIGNED",
            previous_status=onboarding.status,
            changed_by=actor_id,
            notes=f"Assigned to internal reviewer {reviewer.id}.",
        )
        await self._audit_event(
            AuditEventType.PARTNER_ONBOARDING_ASSIGNED,
            onboarding,
            actor_id=actor_id,
            actor_email=actor_email,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await self.db.commit()
        await self.db.refresh(onboarding)
        return onboarding

    async def update_business_information(
        self,
        *,
        onboarding_id: UUID,
        data: PartnerBusinessInformationUpdate,
        actor_id: UUID,
        actor_email: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> PartnerOnboarding:
        onboarding = await self._get_mutable_request(onboarding_id, for_update=True)
        if onboarding.status not in {
            PartnerOnboardingStatus.REQUESTED,
            PartnerOnboardingStatus.BUSINESS_INFORMATION,
        }:
            raise conflict(
                "Business information can only be edited before compliance review "
                "begins."
            )
        await self._apply_business_information(onboarding, data)
        onboarding.updated_at = utc_now()
        await self.repository.add_history(
            onboarding=onboarding,
            action="BUSINESS_INFORMATION_UPDATED",
            previous_status=onboarding.status,
            changed_by=actor_id,
            notes="Partner business information updated by platform staff.",
        )
        await self._audit_event(
            AuditEventType.PARTNER_ONBOARDING_UPDATED,
            onboarding,
            actor_id=actor_id,
            actor_email=actor_email,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await self.db.commit()
        await self.db.refresh(onboarding)
        return onboarding

    async def _apply_business_information(
        self,
        onboarding: PartnerOnboarding,
        data: PartnerBusinessInformationUpdate,
    ) -> None:
        values = data.model_dump(exclude_unset=True)
        if not values:
            raise bad_request("No business information fields were provided.")
        if values.get("contact_email") is not None:
            email = str(values["contact_email"]).strip().lower()
            if await self.repository.has_open_request_for_email(
                email, exclude_id=onboarding.id
            ):
                raise conflict(
                    "An open partner onboarding request already exists for this "
                    "contact email."
                )
            values["contact_email"] = email
        for field, value in values.items():
            if value is None:
                continue
            if isinstance(value, str):
                value = value.strip()
            setattr(onboarding, field, value)

    @staticmethod
    def _require_assignee(onboarding: PartnerOnboarding) -> None:
        if onboarding.assigned_to is None:
            raise conflict(
                "Assign an internal reviewer before progressing this request."
            )

    async def advance_stage(
        self,
        *,
        onboarding_id: UUID,
        actor_id: UUID,
        actor_email: str,
        ip_address: str | None,
        user_agent: str | None,
        notes: str | None,
    ) -> PartnerOnboarding:
        onboarding = await self._get_mutable_request(onboarding_id, for_update=True)
        self._require_assignee(onboarding)
        if onboarding.portal_token_hash:
            await AsyncPartnerOnboardingPortalWriteService(self.db).ensure_can_advance(
                onboarding_id
            )
        next_status = _NEXT_STAGE.get(onboarding.status)
        if next_status is None:
            raise conflict(
                f"Request cannot advance from status {onboarding.status.value}."
            )
        previous_status = onboarding.status
        onboarding.status = next_status
        onboarding.updated_at = utc_now()
        if previous_status == PartnerOnboardingStatus.COMPLIANCE_REVIEW:
            onboarding.reviewed_at = utc_now()
        await self.repository.add_history(
            onboarding=onboarding,
            action="STAGE_CHANGED",
            previous_status=previous_status,
            changed_by=actor_id,
            notes=notes,
        )
        await self._audit_event(
            AuditEventType.PARTNER_ONBOARDING_STAGE_CHANGED,
            onboarding,
            actor_id=actor_id,
            actor_email=actor_email,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await self.db.commit()
        await self.db.refresh(onboarding)
        return onboarding

    async def approve_and_activate(
        self,
        *,
        onboarding_id: UUID,
        actor_id: UUID,
        actor_email: str,
        ip_address: str | None,
        user_agent: str | None,
        notes: str | None,
    ) -> PartnerOnboarding:
        onboarding = await self._get_mutable_request(onboarding_id, for_update=True)
        self._require_assignee(onboarding)
        if onboarding.status != PartnerOnboardingStatus.API_CREDENTIALS:
            raise conflict(
                "Partner must complete business information, compliance review, "
                "technical setup, and API credential setup before activation."
            )
        if onboarding.activated_tenant_id is not None:
            raise conflict("This onboarding request has already activated a tenant.")
        tenant = Tenant(
            name=onboarding.organization_name,
            code=self._tenant_code(onboarding.organization_name),
            status=TenantStatus.ACTIVE,
        )
        old_tenant_id = self.db.info.get("tenant_id")
        had_tenant_id = "tenant_id" in self.db.info
        try:
            await self.repository.create_tenant(tenant)
            self.db.info["tenant_id"] = tenant.id
            self.db.add(
                Organization(
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
            )
            await self.db.flush()
        except Exception:
            await self.db.rollback()
            raise
        finally:
            if had_tenant_id:
                self.db.info["tenant_id"] = old_tenant_id
            else:
                self.db.info.pop("tenant_id", None)
        previous_status = onboarding.status
        now = utc_now()
        onboarding.status = PartnerOnboardingStatus.ACTIVE
        onboarding.activated_tenant_id = tenant.id
        onboarding.activated_at = now
        onboarding.reviewed_at = onboarding.reviewed_at or now
        onboarding.updated_at = now
        await self.repository.add_history(
            onboarding=onboarding,
            action="APPROVED_AND_ACTIVATED",
            previous_status=previous_status,
            changed_by=actor_id,
            notes=notes or "Partner approved; tenant and organization activated.",
        )
        await self._audit_event(
            AuditEventType.PARTNER_ONBOARDING_APPROVED,
            onboarding,
            actor_id=actor_id,
            actor_email=actor_email,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await self.db.commit()
        await self.db.refresh(onboarding)
        return onboarding

    @staticmethod
    def _tenant_code(name: str) -> str:
        slug = re.sub(r"[^A-Z0-9]+", "-", name.upper()).strip("-")
        return f"{(slug or 'PARTNER')[:38]}-{uuid4().hex[:8].upper()}"

    async def reject(
        self,
        *,
        onboarding_id: UUID,
        reason: str,
        actor_id: UUID,
        actor_email: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> PartnerOnboarding:
        onboarding = await self._get_mutable_request(onboarding_id, for_update=True)
        previous_status = onboarding.status
        onboarding.status = PartnerOnboardingStatus.REJECTED
        onboarding.rejection_reason = reason.strip()
        onboarding.reviewed_at = utc_now()
        onboarding.updated_at = utc_now()
        await self.repository.add_history(
            onboarding=onboarding,
            action="REJECTED",
            previous_status=previous_status,
            changed_by=actor_id,
            notes=reason.strip(),
        )
        await self._audit_event(
            AuditEventType.PARTNER_ONBOARDING_REJECTED,
            onboarding,
            actor_id=actor_id,
            actor_email=actor_email,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await self.db.commit()
        await self.db.refresh(onboarding)
        return onboarding


class AsyncPartnerOnboardingPortalWriteService(AsyncPartnerOnboardingWriteService):
    """Async customer-token portal mutations and portal-backed activation."""

    async def _get_portal_request(
        self, onboarding_id: UUID, token: str, *, for_update: bool = False
    ) -> PartnerOnboarding:
        statement = (
            select(PartnerOnboarding)
            .options(
                selectinload(PartnerOnboarding.documents),
                selectinload(PartnerOnboarding.administrators),
            )
            .where(PartnerOnboarding.id == onboarding_id)
        )
        if for_update:
            statement = statement.with_for_update()
        onboarding = await self.db.scalar(statement)
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
            onboarding.documents, key=lambda item: (item.created_at, str(item.id))
        ):
            latest[document.document_type] = document
        return latest

    def _required_documents_submitted(self, onboarding: PartnerOnboarding) -> bool:
        latest = self._latest_documents(onboarding)
        return all(
            key in latest and latest[key].review_status != "REJECTED"
            for key in REQUIRED_DOCUMENT_TYPES
        )

    def _required_documents_approved(self, onboarding: PartnerOnboarding) -> bool:
        latest = self._latest_documents(onboarding)
        return all(
            key in latest and latest[key].review_status == "APPROVED"
            for key in REQUIRED_DOCUMENT_TYPES
        )

    async def _admin_emails_are_available(self, onboarding: PartnerOnboarding) -> None:
        for administrator in onboarding.administrators:
            existing = await self.repository.get_existing_user_id_by_email(
                administrator.email
            )
            if existing is not None:
                raise conflict(
                    f"Administrator email {administrator.email} already belongs "
                    "to a FinPilot user."
                )

    async def create_portal_request(
        self,
        data: PartnerOnboardingCreate,
        *,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[PartnerOnboarding, str]:
        email = str(data.contact_email).strip().lower()
        if await self.repository.has_open_request_for_email(email):
            raise conflict(
                "An open partner onboarding request already exists for this contact "
                "email."
            )
        raw_token = secrets.token_urlsafe(32)
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
            portal_token_hash=_hash_token(raw_token),
            portal_token_expires_at=utc_now() + timedelta(days=PORTAL_TOKEN_TTL_DAYS),
        )
        try:
            await self.repository.create(onboarding)
            await self.repository.add_history(
                onboarding=onboarding,
                action="PORTAL_REQUESTED",
                previous_status=None,
                changed_by=None,
                notes="Self-service partner onboarding portal created.",
            )
            await self._audit_event(
                AuditEventType.PARTNER_ONBOARDING_CREATED,
                onboarding,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
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
        await self.db.refresh(onboarding)
        return onboarding, raw_token

    async def update_business_information_with_portal_token(
        self,
        *,
        onboarding_id: UUID,
        token: str,
        data: PartnerBusinessInformationUpdate,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> PartnerOnboarding:
        onboarding = await self._get_portal_request(
            onboarding_id, token, for_update=True
        )
        if onboarding.status not in {
            PartnerOnboardingStatus.REQUESTED,
            PartnerOnboardingStatus.BUSINESS_INFORMATION,
        }:
            raise conflict(
                "Business information can only be changed before compliance review."
            )
        await self._apply_business_information(onboarding, data)
        onboarding.updated_at = utc_now()
        await self.repository.add_history(
            onboarding=onboarding,
            action="BUSINESS_INFORMATION_UPDATED",
            previous_status=onboarding.status,
            changed_by=None,
            notes="Business information updated by the authenticated portal token.",
        )
        await self._audit_event(
            AuditEventType.PARTNER_ONBOARDING_UPDATED,
            onboarding,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await self.db.commit()
        await self.db.refresh(onboarding)
        return onboarding

    async def add_administrator(
        self,
        *,
        onboarding_id: UUID,
        token: str,
        data: PartnerOnboardingAdministratorCreate,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[PartnerOnboardingAdministrator, str]:
        onboarding = await self._get_portal_request(
            onboarding_id, token, for_update=True
        )
        email = str(data.email).strip().lower()
        if await self.repository.get_existing_user_id_by_email(email) is not None:
            raise conflict(
                "This email already belongs to a FinPilot user. Nominate a different "
                "administrator email."
            )
        if any(item.email.lower() == email for item in onboarding.administrators):
            raise conflict("This administrator has already been added to onboarding.")
        raw_token = secrets.token_urlsafe(32)
        administrator = PartnerOnboardingAdministrator(
            onboarding_id=onboarding.id,
            first_name=data.first_name.strip(),
            last_name=data.last_name.strip(),
            email=email,
            role=UserRole.ADMINISTRATOR.value,
            department=data.department,
            invitation_token_hash=_hash_token(raw_token),
            status="PENDING",
        )
        try:
            await self.repository.create_administrator(administrator)
            await self.repository.add_history(
                onboarding=onboarding,
                action="ADMINISTRATOR_NOMINATED",
                previous_status=onboarding.status,
                changed_by=None,
                notes=f"Administrator nomination recorded for {email}.",
            )
            await self._audit_event(
                AuditEventType.PARTNER_ONBOARDING_UPDATED,
                onboarding,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            raise conflict("This administrator has already been added.") from exc
        await self.db.refresh(administrator)
        return administrator, raw_token

    async def save_technical_setup(
        self,
        *,
        onboarding_id: UUID,
        token: str,
        data: PartnerTechnicalSetupUpdate,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> PartnerOnboarding:
        onboarding = await self._get_portal_request(
            onboarding_id, token, for_update=True
        )
        if onboarding.status == PartnerOnboardingStatus.API_CREDENTIALS:
            raise conflict("Technical setup can no longer be changed at this stage.")
        onboarding.technical_setup = data.model_dump(mode="json")
        onboarding.technical_setup_completed_at = utc_now()
        onboarding.updated_at = utc_now()
        await self.repository.add_history(
            onboarding=onboarding,
            action="TECHNICAL_SETUP_COMPLETED",
            previous_status=onboarding.status,
            changed_by=None,
            notes="Customer technical setup details submitted.",
        )
        await self._audit_event(
            AuditEventType.PARTNER_ONBOARDING_UPDATED,
            onboarding,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await self.db.commit()
        await self.db.refresh(onboarding)
        return onboarding

    async def submit_for_review(
        self,
        *,
        onboarding_id: UUID,
        token: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> PartnerOnboarding:
        onboarding = await self._get_portal_request(
            onboarding_id, token, for_update=True
        )
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
        await self.repository.add_history(
            onboarding=onboarding,
            action="SUBMITTED_FOR_REVIEW",
            previous_status=previous_status,
            changed_by=None,
            notes="Portal submission passed required-step validation.",
        )
        await self._audit_event(
            AuditEventType.PARTNER_ONBOARDING_UPDATED,
            onboarding,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await self.db.commit()
        await self.db.refresh(onboarding)
        return onboarding

    async def ensure_can_advance(self, onboarding_id: UUID) -> None:
        onboarding = await self.db.scalar(
            select(PartnerOnboarding)
            .options(
                selectinload(PartnerOnboarding.documents),
                selectinload(PartnerOnboarding.administrators),
            )
            .where(PartnerOnboarding.id == onboarding_id)
        )
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
            await self._admin_emails_are_available(onboarding)

    async def review_document(
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
        onboarding = await self.repository.get_by_id(onboarding_id, for_update=True)
        if onboarding is None:
            raise not_found("Partner onboarding request")
        if onboarding.status != PartnerOnboardingStatus.COMPLIANCE_REVIEW:
            raise conflict("Documents can only be reviewed during compliance review.")
        document = await self.repository.get_document(onboarding_id, document_id)
        if document is None:
            raise not_found("Partner onboarding document")
        document.review_status = review_status
        document.review_notes = notes
        document.reviewed_by = actor_id
        document.reviewed_at = utc_now()
        onboarding.updated_at = utc_now()
        await self.repository.add_history(
            onboarding=onboarding,
            action="DOCUMENT_REVIEWED",
            previous_status=onboarding.status,
            changed_by=actor_id,
            notes=f"{document.document_type}: {review_status}. {notes or ''}".strip(),
        )
        await self.audit.log_event(
            event_type=AuditEventType.PARTNER_ONBOARDING_UPDATED,
            user_id=actor_id,
            email=actor_email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="partner_onboarding_document",
            resource_id=document.id,
        )
        await self.db.commit()
        await self.db.refresh(document)
        return document

    async def activate_and_issue_credentials(
        self,
        *,
        onboarding_id: UUID,
        actor_id: UUID,
        actor_email: str,
        ip_address: str | None,
        user_agent: str | None,
        notes: str | None,
    ) -> tuple[PartnerOnboarding, str]:
        onboarding = await self.db.scalar(
            select(PartnerOnboarding)
            .options(
                selectinload(PartnerOnboarding.documents),
                selectinload(PartnerOnboarding.administrators),
            )
            .where(PartnerOnboarding.id == onboarding_id)
            .with_for_update()
        )
        if onboarding is None:
            raise not_found("Partner onboarding request")
        if onboarding.status in _TERMINAL_STATUSES:
            raise conflict("This onboarding request is already in a terminal state.")
        if onboarding.status != PartnerOnboardingStatus.API_CREDENTIALS:
            raise conflict(
                "Complete business information, compliance review, and technical "
                "setup before activation."
            )
        self._require_assignee(onboarding)
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
        await self._admin_emails_are_available(onboarding)

        tenant = Tenant(
            name=onboarding.organization_name,
            code=AsyncPartnerOnboardingWriteService._tenant_code(
                onboarding.organization_name
            ),
            status=TenantStatus.ACTIVE,
        )
        raw_api_key = f"fp_live_{secrets.token_urlsafe(32)}"
        now = utc_now()
        old_tenant_id = self.db.info.get("tenant_id")
        had_tenant_id = "tenant_id" in self.db.info
        api_key: APIKey
        try:
            await self.repository.create_tenant(tenant)
            self.db.info["tenant_id"] = tenant.id
            self.db.add(
                Organization(
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
            )
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
                await self.repository.create_invitation(invitation)
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
            await self.repository.create_api_key(api_key)
        except Exception:
            await self.db.rollback()
            raise
        finally:
            if had_tenant_id:
                self.db.info["tenant_id"] = old_tenant_id
            else:
                self.db.info.pop("tenant_id", None)

        previous_status = onboarding.status
        onboarding.status = PartnerOnboardingStatus.ACTIVE
        onboarding.activated_tenant_id = tenant.id
        onboarding.activated_at = now
        onboarding.reviewed_at = onboarding.reviewed_at or now
        onboarding.updated_at = now
        await self.repository.add_history(
            onboarding=onboarding,
            action="CREDENTIALS_GENERATED",
            previous_status=previous_status,
            changed_by=actor_id,
            notes="Initial API credential and administrator invitations were created.",
        )
        await self.repository.add_history(
            onboarding=onboarding,
            action="APPROVED_AND_ACTIVATED",
            previous_status=previous_status,
            changed_by=actor_id,
            notes=notes or "Partner approved; tenant and organization activated.",
        )
        old_tenant_id = self.db.info.get("tenant_id")
        had_tenant_id = "tenant_id" in self.db.info
        self.db.info["tenant_id"] = tenant.id
        try:
            await self.audit.log_event(
                event_type=AuditEventType.PARTNER_ONBOARDING_APPROVED,
                user_id=actor_id,
                email=actor_email,
                ip_address=ip_address,
                user_agent=user_agent,
                resource_type="partner_onboarding",
                resource_id=onboarding.id,
            )
            await self.audit.log_event(
                event_type=AuditEventType.API_KEY_CREATED,
                user_id=actor_id,
                email=actor_email,
                ip_address=ip_address,
                user_agent=user_agent,
                resource_type="api_key",
                resource_id=api_key.id,
            )
        finally:
            if had_tenant_id:
                self.db.info["tenant_id"] = old_tenant_id
            else:
                self.db.info.pop("tenant_id", None)
        await self.db.commit()
        await self.db.refresh(onboarding)
        return onboarding, raw_api_key
