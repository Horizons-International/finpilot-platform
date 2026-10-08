from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.organization import Organization


class OrganizationRepository:
    def __init__(
        self,
        db: Session,
        tenant_id: UUID,
    ) -> None:
        self.db = db
        self.tenant_id = tenant_id

    def create(
        self,
        organization: Organization,
    ) -> Organization:
        self.db.add(organization)
        self.db.flush()
        self.db.refresh(organization)

        return organization

    def get_by_id(
        self,
        organization_id: UUID,
    ) -> Organization | None:
        statement = select(Organization).where(
            Organization.id == organization_id,
            Organization.tenant_id == self.tenant_id,
        )

        return self.db.scalar(statement)

    def get_current(
        self,
    ) -> Organization | None:
        statement = select(Organization).where(
            Organization.tenant_id == self.tenant_id,
        )

        return self.db.scalar(statement)

    def update(
        self,
        organization: Organization,
    ) -> Organization:
        self.db.flush()
        self.db.refresh(organization)

        return organization
