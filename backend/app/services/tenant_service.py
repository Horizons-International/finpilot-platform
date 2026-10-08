from uuid import UUID

from sqlalchemy.orm import Session

from app.models.tenant import Tenant
from app.repositories.tenant_repository import TenantRepository
from app.schemas.tenant import TenantCreate
from app.utils.enums import TenantStatus
from app.utils.errors import bad_request, not_found


class TenantService:
    def __init__(
        self,
        db: Session,
    ) -> None:
        self.db = db
        self.repository = TenantRepository(db)

    def create(
        self,
        data: TenantCreate,
    ) -> Tenant:
        code = data.code.strip().upper()
        name = data.name.strip()

        if self.repository.get_by_code(code) is not None:
            raise bad_request(
                "A tenant with this code already exists.",
            )

        tenant = Tenant(
            name=name,
            code=code,
            status=TenantStatus.ACTIVE,
        )

        self.repository.create(tenant)

        self.db.commit()
        self.db.refresh(tenant)

        return tenant

    def get(
        self,
        tenant_id: UUID,
    ) -> Tenant:
        tenant = self.repository.get_by_id(
            tenant_id,
        )

        if tenant is None:
            raise not_found("Tenant")

        return tenant

    def list(self) -> list[Tenant]:
        return self.repository.list_all()
