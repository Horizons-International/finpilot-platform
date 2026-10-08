from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.tenant import Tenant
from app.utils.enums import TenantStatus


class TenantRepository:
    def __init__(
        self,
        db: Session,
    ) -> None:
        self.db = db

    def get_by_id(
        self,
        tenant_id: UUID,
    ) -> Tenant | None:
        return self.db.get(
            Tenant,
            tenant_id,
        )

    def get_by_code(
        self,
        code: str,
    ) -> Tenant | None:
        statement = select(Tenant).where(
            Tenant.code == code,
        )

        return self.db.scalars(
            statement,
        ).first()

    def list_all(self) -> list[Tenant]:
        statement = select(Tenant).order_by(
            Tenant.name.asc(),
        )

        return list(self.db.scalars(statement).all())

    def create(
        self,
        tenant: Tenant,
    ) -> Tenant:
        self.db.add(tenant)
        self.db.flush()
        self.db.refresh(tenant)

        return tenant

    def is_active(
        self,
        tenant_id: UUID,
    ) -> bool:
        statement = select(Tenant.id).where(
            Tenant.id == tenant_id,
            Tenant.status == TenantStatus.ACTIVE,
        )

        return self.db.execute(statement).first() is not None
