"""Native-async organization-profile management."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization
from app.schemas.organization import OrganizationCreate, OrganizationUpdate
from app.services.async_audit_service import AsyncAuditService
from app.utils.date_time import utc_now
from app.utils.enums import AuditEventType
from app.utils.errors import bad_request, conflict, not_found


class AsyncOrganizationService:
    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        if db.info.get("tenant_id") not in (None, tenant_id):
            raise ValueError("The database session is already bound to another tenant.")
        db.info["tenant_id"] = tenant_id
        self.db, self.tenant_id = db, tenant_id
        self.audit = AsyncAuditService(db)

    async def create(
        self,
        *,
        data: OrganizationCreate,
        user_id: UUID,
        email: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> Organization:
        existing = await self.db.scalar(
            select(Organization)
            .where(Organization.tenant_id == self.tenant_id)
            .with_for_update()
        )
        if existing is not None:
            raise conflict("An organization profile already exists for this tenant.")
        item = Organization(
            tenant_id=self.tenant_id,
            name=data.name,
            legal_name=data.legal_name,
            registration_number=data.registration_number,
            tax_identification_number=data.tax_identification_number,
            industry=data.industry,
            business_description=data.business_description,
            contact_name=data.contact_name,
            contact_email=str(data.contact_email) if data.contact_email else None,
            contact_phone=data.contact_phone,
            website=data.website,
            country=data.country,
            status=data.status,
            settings=data.settings,
        )
        self.db.add(item)
        try:
            await self.db.flush()
            await self.audit.log_event(
                event_type=AuditEventType.ORGANIZATION_CREATED,
                user_id=user_id,
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
                resource_type="organization",
                resource_id=item.id,
            )
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            raise conflict(
                "An organization profile already exists for this tenant."
            ) from exc
        await self.db.refresh(item)
        return item

    async def get(self, organization_id: UUID) -> Organization:
        item = await self.db.scalar(
            select(Organization).where(
                Organization.id == organization_id,
                Organization.tenant_id == self.tenant_id,
            )
        )
        if item is None:
            raise not_found("Organization")
        return item

    async def update(
        self,
        *,
        organization_id: UUID,
        data: OrganizationUpdate,
        user_id: UUID,
        email: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> Organization:
        item = await self.db.scalar(
            select(Organization)
            .where(
                Organization.id == organization_id,
                Organization.tenant_id == self.tenant_id,
            )
            .with_for_update()
        )
        if item is None:
            raise not_found("Organization")
        changes = data.model_dump(exclude_unset=True)
        if not changes:
            raise bad_request("No organization fields were provided for update.")
        changed = False
        for key, value in changes.items():
            if key == "contact_email" and value is not None:
                value = str(value)
            if getattr(item, key) != value:
                setattr(item, key, value)
                changed = True
        if not changed:
            raise bad_request("No organization fields were changed.")
        item.updated_at = utc_now()
        await self.audit.log_event(
            event_type=AuditEventType.ORGANIZATION_UPDATED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="organization",
            resource_id=item.id,
        )
        await self.db.commit()
        await self.db.refresh(item)
        return item
