from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.file import File
from app.models.user import User
from app.repositories.async_tenant_scoped_repository import (
    AsyncTenantScopedRepository,
    resolve_async_tenant_id,
)


class AsyncFileRepository(AsyncTenantScopedRepository[File]):
    def __init__(self, db: AsyncSession, tenant_id: UUID | None = None) -> None:
        resolved_tenant_id = resolve_async_tenant_id(db, tenant_id)
        assert resolved_tenant_id is not None
        super().__init__(db=db, model=File, tenant_id=resolved_tenant_id)

    async def _validate_uploader(self, file_record: File) -> None:
        uploader_id = await self.db.scalar(
            select(User.id).where(
                User.id == file_record.uploaded_by,
                User.tenant_id == self.tenant_id,
            )
        )
        if uploader_id is None:
            raise ValueError("The file uploader does not belong to the current tenant.")

    async def create(self, file_record: File) -> File:
        await self._validate_uploader(file_record)
        return await super().create(file_record)

    async def update(self, file_record: File) -> File:
        await self._validate_uploader(file_record)
        return await super().update(file_record)

    async def get_by_id(self, file_id: UUID) -> File | None:
        return await self.db.scalar(self.query().where(File.id == file_id))
