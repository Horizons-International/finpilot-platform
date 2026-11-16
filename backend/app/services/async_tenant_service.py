"""Async platform-level tenant registry operations."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Tenant
from app.schemas.tenant import TenantCreate
from app.utils.enums import TenantStatus
from app.utils.errors import bad_request, unauthorized


class AsyncTenantService:
    """Tenant registry operations; tenant creation is platform-admin only."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, data: TenantCreate) -> Tenant:
        code = data.code.strip().upper()
        name = data.name.strip()
        existing = await self.db.scalar(select(Tenant.id).where(Tenant.code == code))
        if existing is not None:
            raise bad_request("A tenant with this code already exists.")

        tenant = Tenant(name=name, code=code, status=TenantStatus.ACTIVE)
        self.db.add(tenant)
        try:
            # The unique constraint is the final guard against concurrent creates.
            await self.db.flush()
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            raise bad_request("A tenant with this code already exists.") from exc
        except Exception:
            await self.db.rollback()
            raise
        await self.db.refresh(tenant)
        return tenant

    async def get_current(self, tenant_id: UUID) -> Tenant:
        tenant = await self.db.scalar(select(Tenant).where(Tenant.id == tenant_id))
        if tenant is None:
            raise unauthorized("Tenant not found")
        return tenant
