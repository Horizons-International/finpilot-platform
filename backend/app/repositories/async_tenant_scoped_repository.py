from collections.abc import Mapping
from typing import Generic, TypeVar
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from app.core.database import Base

ModelType = TypeVar("ModelType", bound=Base)


def resolve_async_tenant_id(
    db: AsyncSession,
    tenant_id: UUID | None = None,
    *,
    required: bool = True,
) -> UUID | None:
    """Resolve a trusted tenant ID and reject conflicting session context."""
    session_info = getattr(db, "info", None)
    session_tenant_id = (
        session_info.get("tenant_id") if isinstance(session_info, Mapping) else None
    )

    if session_tenant_id is not None and not isinstance(session_tenant_id, UUID):
        raise ValueError("Session tenant context must be a UUID.")

    if tenant_id is not None and session_tenant_id is not None:
        if tenant_id != session_tenant_id:
            raise ValueError(
                "Repository tenant does not match the active session tenant."
            )

    resolved = tenant_id if tenant_id is not None else session_tenant_id
    if resolved is None and required:
        raise ValueError(
            "Tenant context is required for tenant-scoped repository access."
        )
    if resolved is not None and not isinstance(resolved, UUID):
        raise ValueError("Tenant context must be a UUID.")

    return resolved


class AsyncTenantScopedRepository(Generic[ModelType]):
    """Async repository base for ORM models with a direct ``tenant_id`` column."""

    def __init__(
        self,
        db: AsyncSession,
        model: type[ModelType],
        tenant_id: UUID,
    ) -> None:
        if not hasattr(model, "tenant_id"):
            raise TypeError(f"{model.__name__} does not define tenant_id.")

        resolved_tenant_id = resolve_async_tenant_id(db, tenant_id)
        assert resolved_tenant_id is not None

        self.db = db
        self.model = model
        self.tenant_id = resolved_tenant_id

    def query(self) -> Select[ModelType]:
        """Return a SELECT statement explicitly restricted to this tenant."""
        return select(self.model).where(
            getattr(self.model, "tenant_id") == self.tenant_id,
        )

    async def get_by_id(self, entity_id: UUID) -> ModelType | None:
        statement = self.query().where(getattr(self.model, "id") == entity_id)
        return await self.db.scalar(statement)

    async def get_all(self) -> list[ModelType]:
        result = await self.db.scalars(self.query())
        return list(result.all())

    async def create(self, entity: ModelType) -> ModelType:
        """Bind trusted tenant ownership before inserting an entity."""
        entity_tenant_id = getattr(entity, "tenant_id", None)
        if entity_tenant_id is not None and entity_tenant_id != self.tenant_id:
            raise ValueError("Cannot create an entity for another tenant.")

        setattr(entity, "tenant_id", self.tenant_id)
        self.db.add(entity)
        await self.db.flush()
        await self.db.refresh(entity)
        return entity

    async def update(self, entity: ModelType) -> ModelType:
        entity_tenant_id = getattr(entity, "tenant_id", None)
        if entity_tenant_id != self.tenant_id:
            raise ValueError("Cannot update an entity owned by another tenant.")

        await self.db.flush()
        await self.db.refresh(entity)
        return entity

    async def delete(self, entity: ModelType) -> None:
        entity_tenant_id = getattr(entity, "tenant_id", None)
        if entity_tenant_id != self.tenant_id:
            raise ValueError("Cannot delete an entity owned by another tenant.")

        await self.db.delete(entity)
        await self.db.flush()
