from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge_document import KnowledgeDocument
from app.models.user import User
from app.repositories.async_tenant_scoped_repository import (
    AsyncTenantScopedRepository,
    resolve_async_tenant_id,
)
from app.utils.enums import KnowledgeDocumentStatus


class AsyncKnowledgeDocumentRepository(AsyncTenantScopedRepository[KnowledgeDocument]):
    def __init__(self, db: AsyncSession, tenant_id: UUID | None = None) -> None:
        resolved_tenant_id = resolve_async_tenant_id(db, tenant_id)
        assert resolved_tenant_id is not None
        super().__init__(
            db=db,
            model=KnowledgeDocument,
            tenant_id=resolved_tenant_id,
        )

    async def _validate_uploader(self, document: KnowledgeDocument) -> None:
        uploader_id = await self.db.scalar(
            select(User.id).where(
                User.id == document.uploaded_by,
                User.tenant_id == self.tenant_id,
            )
        )
        if uploader_id is None:
            raise ValueError(
                "The knowledge document uploader does not belong to the current tenant."
            )

    async def create(self, document: KnowledgeDocument) -> KnowledgeDocument:
        await self._validate_uploader(document)
        return await super().create(document)

    async def update(self, document: KnowledgeDocument) -> KnowledgeDocument:
        await self._validate_uploader(document)
        return await super().update(document)

    async def get_latest_by_name(self, name: str) -> KnowledgeDocument | None:
        statement = (
            self.query()
            .where(KnowledgeDocument.name == name)
            .order_by(KnowledgeDocument.version.desc())
        )
        result = await self.db.scalars(statement)
        return result.first()

    async def get_by_name_and_version(
        self,
        name: str,
        version: int,
    ) -> KnowledgeDocument | None:
        statement = self.query().where(
            KnowledgeDocument.name == name,
            KnowledgeDocument.version == version,
        )
        result = await self.db.scalars(statement)
        return result.first()

    async def get_active_by_name(self, name: str) -> KnowledgeDocument | None:
        statement = self.query().where(
            KnowledgeDocument.name == name,
            KnowledgeDocument.status == KnowledgeDocumentStatus.ACTIVE,
        )
        result = await self.db.scalars(statement)
        return result.first()

    async def get_all_versions(self, name: str) -> list[KnowledgeDocument]:
        statement = (
            self.query()
            .where(KnowledgeDocument.name == name)
            .order_by(KnowledgeDocument.version.desc())
        )
        result = await self.db.scalars(statement)
        return list(result.all())

    async def get_all_active(self) -> list[KnowledgeDocument]:
        statement = (
            self.query()
            .where(KnowledgeDocument.status == KnowledgeDocumentStatus.ACTIVE)
            .order_by(KnowledgeDocument.name, KnowledgeDocument.version.desc())
        )
        result = await self.db.scalars(statement)
        return list(result.all())

    async def get_all_ordered(self) -> list[KnowledgeDocument]:
        statement = self.query().order_by(
            KnowledgeDocument.name,
            KnowledgeDocument.version.desc(),
        )
        result = await self.db.scalars(statement)
        return list(result.all())
