"""Tenant-scoped persistence for API keys and their usage records."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.api_key import APIKey, APIKeyUsage
from app.repositories.tenant_scoped_repository import TenantScopedRepository


class APIKeyRepository(TenantScopedRepository[APIKey]):
    """Persist and query API credentials for one tenant."""

    def __init__(self, db: Session, tenant_id: UUID) -> None:
        super().__init__(db=db, model=APIKey, tenant_id=tenant_id)

    def list_keys(self) -> list[APIKey]:
        return self.query().order_by(APIKey.created_at.desc()).all()

    def get_key(
        self,
        api_key_id: UUID,
        *,
        for_update: bool = False,
    ) -> APIKey | None:
        query = self.query().filter(APIKey.id == api_key_id)
        if for_update:
            query = query.with_for_update()
        return query.first()

    def list_usage(
        self,
        api_key_id: UUID,
        *,
        limit: int = 100,
    ) -> list[APIKeyUsage]:
        statement = (
            select(APIKeyUsage)
            .where(
                APIKeyUsage.tenant_id == self.tenant_id,
                APIKeyUsage.api_key_id == api_key_id,
            )
            .order_by(APIKeyUsage.created_at.desc())
            .limit(limit)
        )
        return list(self.db.scalars(statement).all())
