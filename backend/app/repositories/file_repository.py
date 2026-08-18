from uuid import UUID

from sqlalchemy.orm import Session

from app.models.file import File
from app.repositories.base_repository import BaseRepository


class FileRepository(BaseRepository[File]):
    def __init__(self, db: Session):
        super().__init__(db, File)

    def get_by_id(self, file_id: UUID) -> File | None:
        return self.db.query(File).filter(File.id == file_id).first()

    def create(self, entity: File) -> File:
        self.db.add(entity)
        self.db.commit()
        self.db.refresh(entity)
        return entity

    def delete(self, entity: File) -> None:
        self.db.delete(entity)
        self.db.commit()
