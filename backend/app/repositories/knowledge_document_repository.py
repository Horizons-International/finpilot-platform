from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.models.knowledge_document import KnowledgeDocument
from app.repositories.base_repository import BaseRepository
from app.utils.enums import KnowledgeDocumentStatus


class KnowledgeDocumentRepository(BaseRepository[KnowledgeDocument]):
    def __init__(self, db: Session) -> None:
        super().__init__(db, KnowledgeDocument)

    def get_latest_by_name(
        self,
        name: str,
    ) -> KnowledgeDocument | None:
        return (
            self.db.query(KnowledgeDocument)
            .filter(KnowledgeDocument.name == name)
            .order_by(
                KnowledgeDocument.version.desc(),
            )
            .first()
        )

    def get_by_name_and_version(
        self,
        name: str,
        version: int,
    ) -> KnowledgeDocument | None:
        return (
            self.db.query(KnowledgeDocument)
            .filter(
                and_(
                    KnowledgeDocument.name == name,
                    KnowledgeDocument.version == version,
                )
            )
            .first()
        )

    def get_active_by_name(
        self,
        name: str,
    ) -> KnowledgeDocument | None:
        return (
            self.db.query(KnowledgeDocument)
            .filter(
                and_(
                    KnowledgeDocument.name == name,
                    KnowledgeDocument.status == KnowledgeDocumentStatus.ACTIVE,
                )
            )
            .first()
        )

    def get_all_versions(
        self,
        name: str,
    ) -> list[KnowledgeDocument]:
        return (
            self.db.query(KnowledgeDocument)
            .filter(KnowledgeDocument.name == name)
            .order_by(
                KnowledgeDocument.version.desc(),
            )
            .all()
        )

    def get_all_active(
        self,
    ) -> list[KnowledgeDocument]:
        return (
            self.db.query(KnowledgeDocument)
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
            self.db.query(KnowledgeDocument)
            .order_by(
                KnowledgeDocument.name,
                KnowledgeDocument.version.desc(),
            )
            .all()
        )
