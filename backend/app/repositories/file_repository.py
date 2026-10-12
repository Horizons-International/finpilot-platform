from uuid import UUID

from sqlalchemy.orm import Session

from app.models.file import File
from app.models.user import User
from app.repositories.tenant_scoped_repository import TenantScopedRepository


class FileRepository(TenantScopedRepository[File]):
    def __init__(self, db: Session, tenant_id: UUID | None = None) -> None:
        resolved_tenant_id = (
            tenant_id if tenant_id is not None else db.info.get("tenant_id")
        )
        if not isinstance(resolved_tenant_id, UUID):
            raise ValueError("A tenant context is required for files.")
        super().__init__(db=db, model=File, tenant_id=resolved_tenant_id)

    def _validate_uploader(self, file_record: File) -> None:
        uploader_exists = (
            self.db.query(User.id)
            .filter(
                User.id == file_record.uploaded_by,
                User.tenant_id == self.tenant_id,
            )
            .first()
        )
        if uploader_exists is None:
            raise ValueError("The file uploader does not belong to the current tenant.")

    def create(self, file_record: File) -> File:
        self._validate_uploader(file_record)
        return super().create(file_record)

    def update(self, file_record: File) -> File:
        self._validate_uploader(file_record)
        return super().update(file_record)

    def get_by_id(self, file_id: UUID) -> File | None:
        return self.query().filter(File.id == file_id).first()
