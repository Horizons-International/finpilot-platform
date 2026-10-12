from uuid import UUID

from sqlalchemy.orm import Session

from app.models.organization import Organization
from app.repositories.tenant_scoped_repository import TenantScopedRepository


class OrganizationRepository(TenantScopedRepository[Organization]):
    def __init__(self, db: Session, tenant_id: UUID) -> None:
        super().__init__(db=db, model=Organization, tenant_id=tenant_id)

    def create(self, organization: Organization) -> Organization:
        existing_tenant_id = organization.tenant_id
        if existing_tenant_id is not None and existing_tenant_id != self.tenant_id:
            raise ValueError("Cannot create an organization for another tenant.")
        return super().create(organization)

    def get_by_id(self, organization_id: UUID) -> Organization | None:
        return self.query().filter(Organization.id == organization_id).first()

    def get_current(self) -> Organization | None:
        return self.query().first()

    def update(self, organization: Organization) -> Organization:
        if organization.tenant_id != self.tenant_id:
            raise ValueError("Cannot update an organization owned by another tenant.")
        return super().update(organization)
