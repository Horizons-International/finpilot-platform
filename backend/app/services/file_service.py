from uuid import UUID

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.file import File
from app.repositories.file_repository import FileRepository
from app.services.audit_service import AuditService
from app.storages.base_storage import BaseStorage
from app.utils.enums import AuditEventType
from app.utils.errors import bad_request, not_found
from app.utils.files import get_filename


class FileService:
    def __init__(
        self,
        db: Session,
        storage: BaseStorage,
    ):
        self.db = db
        self.file_repository = FileRepository(db)
        self.audit_service = AuditService(db)
        self.storage = storage

    async def upload_file(
        self,
        file: UploadFile,
        uploaded_by: UUID,
        module: str,
        folder: str,
    ) -> File:
        # Validate filename
        if not file.filename:
            raise bad_request("Filename is required.")

        # Validate file type
        if file.content_type is None:
            raise bad_request("File content type is required.")

        if file.content_type not in settings.ALLOWED_FILE_TYPES:
            raise bad_request("File type is not supported.")

        # Read file
        file_content = await file.read()

        # Validate file size
        if len(file_content) > settings.MAX_FILE_SIZE:
            raise bad_request("File size exceeds the maximum allowed size.")

        storage_path: str | None = None

        try:
            # Store physical file
            storage_path = self.storage.save(
                file_content=file_content,
                filename=file.filename,
                folder=f"{module}/{folder}",
            )

            stored_filename = get_filename(storage_path)

            # Create database record
            file_record = File(
                original_filename=file.filename,
                stored_filename=stored_filename,
                storage_path=storage_path,
                folder=folder,
                module=module,
                content_type=file.content_type,
                file_size=len(file_content),
                uploaded_by=uploaded_by,
            )

            self.file_repository.create(file_record)

            # Create audit record
            self.audit_service.log_event(
                event_type=AuditEventType.FILE_UPLOAD,
                user_id=uploaded_by,
                resource_type="file",
                resource_id=file_record.id,
            )

            # Commit file metadata + audit record together
            self.db.commit()

            # Refresh so the returned object contains committed DB values
            self.db.refresh(file_record)

            return file_record

        except Exception:
            # Roll back database changes
            self.db.rollback()

            # Remove physical file if it was already created
            if storage_path is not None:
                try:
                    if self.storage.exists(storage_path):
                        self.storage.delete(storage_path)
                except Exception:
                    # Do not hide the original exception
                    pass

            raise

    def download_file(
        self,
        file_id: UUID,
        user_id: UUID,
    ) -> tuple[bytes, str, str]:
        file_record = self.file_repository.get_by_id(file_id)

        if not file_record:
            raise not_found("File")

        if not self.storage.exists(file_record.storage_path):
            raise not_found("Stored file")

        content = self.storage.read(
            file_record.storage_path,
        )

        try:
            # Record successful download
            self.audit_service.log_event(
                event_type=AuditEventType.FILE_DOWNLOAD,
                user_id=user_id,
                resource_type="file",
                resource_id=file_record.id,
            )

            self.db.commit()

        except Exception:
            self.db.rollback()
            raise

        return (
            content,
            file_record.original_filename,
            file_record.content_type,
        )

    def delete_file(
        self,
        file_id: UUID,
        user_id: UUID,
    ) -> None:
        file_record = self.file_repository.get_by_id(file_id)

        if not file_record:
            raise not_found("File")

        storage_path = file_record.storage_path

        try:
            # Delete physical file
            self.storage.delete(storage_path)

            # Delete database metadata
            self.file_repository.delete(file_record)

            # Record successful deletion
            self.audit_service.log_event(
                event_type=AuditEventType.FILE_DELETE,
                user_id=user_id,
                resource_type="file",
                resource_id=file_id,
            )

            # Commit metadata deletion + audit record together
            self.db.commit()

        except Exception:
            self.db.rollback()
            raise
