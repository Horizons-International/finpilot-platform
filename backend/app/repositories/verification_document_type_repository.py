from uuid import UUID

from sqlalchemy.orm import Session

from app.models.verification_document_type import VerificationDocumentType
from app.repositories.base_repository import BaseRepository


class VerificationDocumentTypeRepository(BaseRepository[VerificationDocumentType]):
    def __init__(self, db: Session) -> None:
        super().__init__(db, VerificationDocumentType)

    def get_by_id(
        self,
        document_type_id: UUID,
    ) -> VerificationDocumentType | None:
        return (
            self.db.query(VerificationDocumentType)
            .filter(VerificationDocumentType.id == document_type_id)
            .first()
        )

    def get_by_name(
        self,
        name: str,
    ) -> VerificationDocumentType | None:
        return (
            self.db.query(VerificationDocumentType)
            .filter(VerificationDocumentType.name == name)
            .first()
        )

    def get_active(self) -> list[VerificationDocumentType]:
        return (
            self.db.query(VerificationDocumentType)
            .filter(VerificationDocumentType.is_active.is_(True))
            .order_by(VerificationDocumentType.name.asc())
            .all()
        )

    def get_all(self) -> list[VerificationDocumentType]:
        return (
            self.db.query(VerificationDocumentType)
            .order_by(VerificationDocumentType.name.asc())
            .all()
        )
