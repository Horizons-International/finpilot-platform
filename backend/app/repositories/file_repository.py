from uuid import UUID

from sqlalchemy.orm import Session

from app.models.file import File
from app.repositories.tenant_scoped_repository import (
    TenantScopedRepository,
)


class FileRepository(TenantScopedRepository[File]):
    def __init__(
        self,
        db: Session,
        tenant_id: UUID,
    ) -> None:
        super().__init__(
            db=db,
            model=File,
            tenant_id=tenant_id,
        )

    def get_by_id(
        self,
        file_id: UUID,
    ) -> File | None:
        return self.query().filter(File.id == file_id).first()
