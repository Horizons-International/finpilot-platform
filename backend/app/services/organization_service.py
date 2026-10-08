from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.organization import Organization
from app.repositories.organization_repository import (
    OrganizationRepository,
)
from app.schemas.organization import (
    OrganizationCreate,
    OrganizationUpdate,
)
from app.services.audit_service import AuditService
from app.utils.date_time import utc_now
from app.utils.enums import AuditEventType
from app.utils.errors import (
    bad_request,
    conflict,
    not_found,
)


class OrganizationService:
    def __init__(
        self,
        db: Session,
        tenant_id: UUID,
    ) -> None:
        self.db = db
        self.tenant_id = tenant_id

        self.repository = OrganizationRepository(
            db=db,
            tenant_id=tenant_id,
        )

        self.audit_service = AuditService(db)

    def create(
        self,
        *,
        data: OrganizationCreate,
        user_id: UUID,
        email: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> Organization:
        if self.repository.get_current() is not None:
            raise conflict(
                "An organization profile already exists for this tenant.",
            )

        organization = Organization(
            tenant_id=self.tenant_id,
            name=data.name,
            legal_name=data.legal_name,
            registration_number=data.registration_number,
            tax_identification_number=data.tax_identification_number,
            industry=data.industry,
            business_description=data.business_description,
            contact_name=data.contact_name,
            contact_email=(
                str(data.contact_email) if data.contact_email is not None else None
            ),
            contact_phone=data.contact_phone,
            website=data.website,
            country=data.country,
            status=data.status,
            settings=data.settings,
        )

        try:
            self.repository.create(
                organization,
            )
            self.db.flush()

        except IntegrityError as exc:
            self.db.rollback()
            raise conflict(
                "An organization profile already exists for this tenant.",
            ) from exc

        self.audit_service.log_event(
            event_type=AuditEventType.ORGANIZATION_CREATED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="organization",
            resource_id=organization.id,
        )

        self.db.commit()
        self.db.refresh(organization)

        return organization

    def get(
        self,
        organization_id: UUID,
    ) -> Organization:
        organization = self.repository.get_by_id(
            organization_id,
        )

        if organization is None:
            raise not_found("Organization")

        return organization

    def update(
        self,
        *,
        organization_id: UUID,
        data: OrganizationUpdate,
        user_id: UUID,
        email: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> Organization:
        organization = self.repository.get_by_id(
            organization_id,
        )

        if organization is None:
            raise not_found("Organization")

        update_data = data.model_dump(
            exclude_unset=True,
        )

        if not update_data:
            raise bad_request(
                "No organization fields were provided for update.",
            )

        changed = False

        for field, new_value in update_data.items():
            if field == "contact_email" and new_value is not None:
                new_value = str(new_value)

            old_value = getattr(
                organization,
                field,
            )

            if old_value != new_value:
                setattr(
                    organization,
                    field,
                    new_value,
                )
                changed = True

        if not changed:
            raise bad_request(
                "No organization fields were changed.",
            )

        organization.updated_at = utc_now()

        self.repository.update(
            organization,
        )

        self.audit_service.log_event(
            event_type=AuditEventType.ORGANIZATION_UPDATED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="organization",
            resource_id=organization.id,
        )

        self.db.commit()
        self.db.refresh(organization)

        return organization
