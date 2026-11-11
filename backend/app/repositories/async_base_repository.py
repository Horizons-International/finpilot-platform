from typing import Generic, TypeVar
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from app.core.database import Base

ModelType = TypeVar("ModelType", bound=Base)


class AsyncBaseRepository(Generic[ModelType]):
    """Base CRUD repository for SQLAlchemy asynchronous sessions."""

    def __init__(
        self,
        db: AsyncSession,
        model: type[ModelType],
    ) -> None:
        self.db = db
        self.model = model

    def query(self) -> Select[ModelType]:
        """Return a SELECT statement for this repository's model."""
        return select(self.model)

    async def get_by_id(self, entity_id: UUID) -> ModelType | None:
        return await self.db.get(self.model, entity_id)

    async def get_all(self) -> list[ModelType]:
        result = await self.db.scalars(self.query())
        return list(result.all())

    async def create(self, entity: ModelType) -> ModelType:
        self.db.add(entity)
        await self.db.flush()
        await self.db.refresh(entity)
        return entity

    async def update(self, entity: ModelType) -> ModelType:
        await self.db.flush()
        await self.db.refresh(entity)
        return entity

    async def delete(self, entity: ModelType) -> None:
        await self.db.delete(entity)
        await self.db.flush()
