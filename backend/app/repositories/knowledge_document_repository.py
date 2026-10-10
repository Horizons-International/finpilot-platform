from uuid import UUID

from sqlalchemy.orm import Session

from app.models.knowledge_document import KnowledgeDocument
from app.repositories.tenant_scoped_repository import (
    TenantScopedRepository,
)
from app.utils.enums import KnowledgeDocumentStatus


class KnowledgeDocumentRepository(TenantScopedRepository[KnowledgeDocument]):
    def __init__(
        self,
        db: Session,
        tenant_id: UUID,
    ) -> None:
        super().__init__(
            db=db,
            model=KnowledgeDocument,
            tenant_id=tenant_id,
        )

    def get_latest_by_name(
        self,
        name: str,
    ) -> KnowledgeDocument | None:
        return (
            self.query()
            .filter(KnowledgeDocument.name == name)
            .order_by(KnowledgeDocument.version.desc())
            .first()
        )

    def get_by_name_and_version(
        self,
        name: str,
        version: int,
    ) -> KnowledgeDocument | None:
        return (
            self.query()
            .filter(
                KnowledgeDocument.name == name,
                KnowledgeDocument.version == version,
            )
            .first()
        )

    def get_active_by_name(
        self,
        name: str,
    ) -> KnowledgeDocument | None:
        return (
            self.query()
            .filter(
                KnowledgeDocument.name == name,
                KnowledgeDocument.status == KnowledgeDocumentStatus.ACTIVE,
            )
            .first()
        )

    def get_all_versions(
        self,
        name: str,
    ) -> list[KnowledgeDocument]:
        return (
            self.query()
            .filter(KnowledgeDocument.name == name)
            .order_by(KnowledgeDocument.version.desc())
            .all()
        )

    def get_all_active(
        self,
    ) -> list[KnowledgeDocument]:
        return (
            self.query()
            .filter(
                KnowledgeDocument.status == KnowledgeDocumentStatus.ACTIVE,
            )
            .order_by(
                KnowledgeDocument.name,
                KnowledgeDocument.version.desc(),
            )
            .all()
        )

    def get_all_ordered(
        self,
    ) -> list[KnowledgeDocument]:
        return (
            self.query()
            .order_by(
                KnowledgeDocument.name,
                KnowledgeDocument.version.desc(),
            )
            .all()
        )
