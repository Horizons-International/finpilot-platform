"""Partner onboarding workflow and tenant activation service."""

import re
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.organization import Organization
from app.models.partner_onboarding import (
    PartnerOnboarding,
    PartnerOnboardingHistory,
)
from app.models.tenant import Tenant
from app.models.user import User
from app.repositories.partner_onboarding_repository import PartnerOnboardingRepository
from app.schemas.partner_onboarding import (
    PartnerBusinessInformationUpdate,
    PartnerOnboardingCreate,
)
from app.services.audit_service import AuditService
from app.utils.date_time import utc_now
from app.utils.enums import (
    AuditEventType,
    OrganizationStatus,
    PartnerOnboardingStatus,
    TenantStatus,
    UserStatus,
)
from app.utils.errors import bad_request, conflict, not_found

_NEXT_STAGE: dict[PartnerOnboardingStatus, PartnerOnboardingStatus] = {
    PartnerOnboardingStatus.REQUESTED: PartnerOnboardingStatus.BUSINESS_INFORMATION,
    PartnerOnboardingStatus.BUSINESS_INFORMATION: (
        PartnerOnboardingStatus.COMPLIANCE_REVIEW
    ),
    PartnerOnboardingStatus.COMPLIANCE_REVIEW: PartnerOnboardingStatus.TECHNICAL_SETUP,
    PartnerOnboardingStatus.TECHNICAL_SETUP: PartnerOnboardingStatus.API_CREDENTIALS,
}

_TERMINAL_STATUSES = {
    PartnerOnboardingStatus.ACTIVE,
    PartnerOnboardingStatus.REJECTED,
}


class PartnerOnboardingService:
    """Manage partner onboarding from public application to active tenant.

    Prospective partners are not tenants yet, so these records are platform-level
    records without a ``tenant_id`` column. All administrative operations must
    be protected by ``require_platform_admin`` in the API router.
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = PartnerOnboardingRepository(db)
        self.audit_service = AuditService(db)

    def create_request(self, data: PartnerOnboardingCreate) -> PartnerOnboarding:
        email = str(data.contact_email).strip().lower()
        duplicate = self.db.scalar(
            select(PartnerOnboarding.id).where(
                PartnerOnboarding.contact_email == email,
                PartnerOnboarding.status != PartnerOnboardingStatus.REJECTED,
            )
        )
        if duplicate is not None:
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
            self.repository.create(onboarding)
            self.repository.add_history(
                onboarding=onboarding,
                action="REQUESTED",
                previous_status=None,
                changed_by=None,
                notes="Partner onboarding request submitted.",
            )
            self.audit_service.log_event(
                event_type=AuditEventType.PARTNER_ONBOARDING_CREATED,
                email=email,
                resource_type="partner_onboarding",
                resource_id=onboarding.id,
            )
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            constraint_name = getattr(
                getattr(exc.orig, "diag", None), "constraint_name", None
            )
            if constraint_name == "uq_partner_onboarding_non_rejected_contact_email":
                raise conflict(
                    "An open partner onboarding request already exists for this "
                    "contact email."
                ) from exc
            raise
        self.db.refresh(onboarding)
        return onboarding

    def list_requests(
        self,
        *,
        status: PartnerOnboardingStatus | None = None,
        assigned_to: UUID | None = None,
    ) -> list[PartnerOnboarding]:
        return self.repository.list_all(status=status, assigned_to=assigned_to)

    def get_request(self, onboarding_id: UUID) -> PartnerOnboarding:
        onboarding = self.repository.get_by_id(onboarding_id)
        if onboarding is None:
            raise not_found("Partner onboarding request")
        return onboarding

    def get_history(self, onboarding_id: UUID) -> list[PartnerOnboardingHistory]:
        self.get_request(onboarding_id)
        return self.repository.history(onboarding_id)

    def assign_reviewer(
        self,
        *,
        onboarding_id: UUID,
        assigned_to: UUID,
        actor_id: UUID,
        actor_email: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> PartnerOnboarding:
        onboarding = self._get_mutable_request(onboarding_id, for_update=True)
        reviewer = self.db.scalar(
            select(User)
            .where(User.id == assigned_to)
            .execution_options(
                skip_tenant_filter=True,
                tenant_scope_reason=(
                    "platform administrator validates a reviewer for global "
                    "partner onboarding"
                ),
            )
        )
        if reviewer is None or not reviewer.is_platform_admin:
            raise bad_request(
                "The assigned reviewer must be an active platform administrator."
            )
        if reviewer.status != UserStatus.ACTIVE or reviewer.is_deleted:
            raise bad_request("The assigned reviewer must be active.")

        onboarding.assigned_to = reviewer.id
        onboarding.updated_at = utc_now()
        self.repository.add_history(
            onboarding=onboarding,
            action="ASSIGNED",
            previous_status=onboarding.status,
            changed_by=actor_id,
            notes=f"Assigned to internal reviewer {reviewer.id}.",
        )
        self._audit(
            AuditEventType.PARTNER_ONBOARDING_ASSIGNED,
            onboarding,
            actor_id,
            actor_email,
            ip_address,
            user_agent,
        )
        self.db.commit()
        self.db.refresh(onboarding)
        return onboarding

    def update_business_information(
        self,
        *,
        onboarding_id: UUID,
        data: PartnerBusinessInformationUpdate,
        actor_id: UUID,
        actor_email: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> PartnerOnboarding:
        onboarding = self._get_mutable_request(onboarding_id, for_update=True)
        if onboarding.status not in {
            PartnerOnboardingStatus.REQUESTED,
            PartnerOnboardingStatus.BUSINESS_INFORMATION,
        }:
            raise conflict(
                "Business information can only be edited before compliance review "
                "begins."
            )
        values = data.model_dump(exclude_unset=True)
        if not values:
            raise bad_request("No business information fields were provided.")
        if values.get("contact_email") is not None:
            normalized_email = str(values["contact_email"]).strip().lower()
            duplicate = self.db.scalar(
                select(PartnerOnboarding.id).where(
                    PartnerOnboarding.id != onboarding.id,
                    PartnerOnboarding.contact_email == normalized_email,
                    PartnerOnboarding.status != PartnerOnboardingStatus.REJECTED,
                )
            )
            if duplicate is not None:
                raise conflict(
                    "An open partner onboarding request already exists for this "
                    "contact email."
                )
            values["contact_email"] = normalized_email
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
            changed_by=actor_id,
            notes="Partner business information updated by platform staff.",
        )
        self._audit(
            AuditEventType.PARTNER_ONBOARDING_UPDATED,
            onboarding,
            actor_id,
            actor_email,
            ip_address,
            user_agent,
        )
        self.db.commit()
        self.db.refresh(onboarding)
        return onboarding

    def advance_stage(
        self,
        *,
        onboarding_id: UUID,
        actor_id: UUID,
        actor_email: str,
        ip_address: str | None,
        user_agent: str | None,
        notes: str | None,
    ) -> PartnerOnboarding:
        onboarding = self._get_mutable_request(onboarding_id, for_update=True)
        self._require_assignee(onboarding)
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
        self.repository.add_history(
            onboarding=onboarding,
            action="STAGE_CHANGED",
            previous_status=previous_status,
            changed_by=actor_id,
            notes=notes,
        )
        self._audit(
            AuditEventType.PARTNER_ONBOARDING_STAGE_CHANGED,
            onboarding,
            actor_id,
            actor_email,
            ip_address,
            user_agent,
        )
        self.db.commit()
        self.db.refresh(onboarding)
        return onboarding

    def approve_and_activate(
        self,
        *,
        onboarding_id: UUID,
        actor_id: UUID,
        actor_email: str,
        ip_address: str | None,
        user_agent: str | None,
        notes: str | None,
    ) -> PartnerOnboarding:
        onboarding = self._get_mutable_request(onboarding_id, for_update=True)
        self._require_assignee(onboarding)
        if onboarding.status != PartnerOnboardingStatus.API_CREDENTIALS:
            raise conflict(
                "Partner must complete business information, compliance review, "
                "technical setup, and API credential setup before activation."
            )
        if onboarding.activated_tenant_id is not None:
            raise conflict("This onboarding request has already activated a tenant.")

        slug = re.sub(r"[^A-Z0-9]+", "-", onboarding.organization_name.upper()).strip(
            "-"
        )
        tenant_code = f"{(slug or 'PARTNER')[:38]}-{uuid4().hex[:8].upper()}"
        tenant = Tenant(
            name=onboarding.organization_name,
            code=tenant_code,
            status=TenantStatus.ACTIVE,
        )
        original_tenant_context = self.db.info.get("tenant_id")
        had_tenant_context = "tenant_id" in self.db.info

        try:
            self.db.add(tenant)
            self.db.flush()

            # Organization is tenant-owned. Temporarily bind the ORM session to
            # the new tenant to let the central before_flush guard validate it.
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
            self.db.add(organization)
            self.db.flush()
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
        onboarding.activated_at = utc_now()
        onboarding.reviewed_at = onboarding.reviewed_at or utc_now()
        onboarding.updated_at = utc_now()
        self.repository.add_history(
            onboarding=onboarding,
            action="APPROVED_AND_ACTIVATED",
            previous_status=previous_status,
            changed_by=actor_id,
            notes=notes or "Partner approved; tenant and organization activated.",
        )
        self._audit(
            AuditEventType.PARTNER_ONBOARDING_APPROVED,
            onboarding,
            actor_id,
            actor_email,
            ip_address,
            user_agent,
        )
        self.db.commit()
        self.db.refresh(onboarding)
        return onboarding

    def reject(
        self,
        *,
        onboarding_id: UUID,
        reason: str,
        actor_id: UUID,
        actor_email: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> PartnerOnboarding:
        onboarding = self._get_mutable_request(onboarding_id, for_update=True)
        if onboarding.status in _TERMINAL_STATUSES:
            raise conflict("An active or rejected request cannot be rejected again.")
        previous_status = onboarding.status
        onboarding.status = PartnerOnboardingStatus.REJECTED
        onboarding.rejection_reason = reason.strip()
        onboarding.reviewed_at = utc_now()
        onboarding.updated_at = utc_now()
        self.repository.add_history(
            onboarding=onboarding,
            action="REJECTED",
            previous_status=previous_status,
            changed_by=actor_id,
            notes=reason.strip(),
        )
        self._audit(
            AuditEventType.PARTNER_ONBOARDING_REJECTED,
            onboarding,
            actor_id,
            actor_email,
            ip_address,
            user_agent,
        )
        self.db.commit()
        self.db.refresh(onboarding)
        return onboarding

    def _get_mutable_request(
        self,
        onboarding_id: UUID,
        *,
        for_update: bool = False,
    ) -> PartnerOnboarding:
        onboarding = self.repository.get_by_id(onboarding_id, for_update=for_update)
        if onboarding is None:
            raise not_found("Partner onboarding request")
        if onboarding.status in _TERMINAL_STATUSES:
            raise conflict("This onboarding request is already in a terminal state.")
        return onboarding

    @staticmethod
    def _require_assignee(onboarding: PartnerOnboarding) -> None:
        if onboarding.assigned_to is None:
            raise conflict(
                "Assign an internal reviewer before progressing this request."
            )

    def _audit(
        self,
        event_type: AuditEventType,
        onboarding: PartnerOnboarding,
        actor_id: UUID,
        actor_email: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> None:
        self.audit_service.log_event(
            event_type=event_type,
            user_id=actor_id,
            email=actor_email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="partner_onboarding",
            resource_id=onboarding.id,
        )
