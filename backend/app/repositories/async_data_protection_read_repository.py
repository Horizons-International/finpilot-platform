from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.data_protection import (
    DataDeletionRequest,
    DataLegalHold,
    DataProtectionPolicy,
)


class AsyncDataProtectionReadRepository:
    """Read-only async queries for tenant-scoped data-protection administration."""

    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        self.db = db
        self.tenant_id = tenant_id
        session_tenant_id = db.info.get("tenant_id")
        if session_tenant_id is not None and session_tenant_id != tenant_id:
            raise ValueError("The session is already bound to another tenant.")
        db.info["tenant_id"] = tenant_id

    async def list_policies(self) -> list[DataProtectionPolicy]:
        result = await self.db.scalars(
            select(DataProtectionPolicy)
            .where(DataProtectionPolicy.tenant_id == self.tenant_id)
            .order_by(DataProtectionPolicy.resource_type)
        )
        return list(result.all())

    async def list_legal_holds(
        self, *, active_only: bool = True, limit: int = 500
    ) -> list[DataLegalHold]:
        statement = select(DataLegalHold).where(
            DataLegalHold.tenant_id == self.tenant_id
        )
        if active_only:
            statement = statement.where(DataLegalHold.active.is_(True))
        result = await self.db.scalars(
            statement.order_by(DataLegalHold.created_at.desc()).limit(limit)
        )
        return list(result.all())

    async def list_deletion_requests(
        self, *, limit: int = 100
    ) -> list[DataDeletionRequest]:
        result = await self.db.scalars(
            select(DataDeletionRequest)
            .where(DataDeletionRequest.tenant_id == self.tenant_id)
            .order_by(DataDeletionRequest.requested_at.desc())
            .limit(limit)
        )
        return list(result.all())
