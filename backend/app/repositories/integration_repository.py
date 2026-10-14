"""Tenant-scoped persistence operations for integrations."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.integration import Integration
from app.utils.enums import IntegrationStatus, IntegrationType


class IntegrationRepository:
    def __init__(self, db: Session, tenant_id: UUID) -> None:
        active_tenant_id = db.info.get("tenant_id")
        if active_tenant_id is not None and active_tenant_id != tenant_id:
            raise ValueError("The SQLAlchemy session is bound to another tenant.")
        db.info["tenant_id"] = tenant_id
        self.db = db
        self.tenant_id = tenant_id

    def create(self, integration: Integration) -> Integration:
        if integration.tenant_id != self.tenant_id:
            raise ValueError("Cannot create an integration for another tenant.")
        self.db.add(integration)
        self.db.flush()
        self.db.refresh(integration)
        return integration

    def get_by_id(self, integration_id: UUID) -> Integration | None:
        return self.db.scalar(
            select(Integration).where(
                Integration.id == integration_id,
                Integration.tenant_id == self.tenant_id,
            )
        )

    def list_all(
        self,
        *,
        integration_type: IntegrationType | None = None,
        status: IntegrationStatus | None = None,
        is_enabled: bool | None = None,
    ) -> list[Integration]:
        filters = [Integration.tenant_id == self.tenant_id]
        if integration_type is not None:
            filters.append(Integration.integration_type == integration_type)
        if status is not None:
            filters.append(Integration.status == status)
        if is_enabled is not None:
            filters.append(Integration.is_enabled == is_enabled)
        statement = (
            select(Integration).where(*filters).order_by(Integration.created_at.desc())
        )
        return list(self.db.scalars(statement).all())
