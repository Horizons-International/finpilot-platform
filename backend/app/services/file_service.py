from pathlib import Path
from uuid import UUID

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.file import File
from app.repositories.file_repository import FileRepository
from app.storage.base_storage import BaseStorage


class FileService:
    def __init__(
        self,
        db: Session,
        storage: BaseStorage,
    ):
        self.file_repository = FileRepository(db)
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
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Filename is required.",
            )

        # Validate file type
        if file.content_type is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File content type is required.",
            )
        if file.content_type not in settings.ALLOWED_FILE_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File type is not supported.",
            )

        # Read file
        file_content = await file.read()

        # Validate file size
        if len(file_content) > settings.MAX_FILE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File size exceeds the maximum allowed size.",
            )

        # Store file
        storage_path = self.storage.save(
            file_content=file_content,
            filename=file.filename,
            folder=f"{module}/{folder}",
        )

        stored_filename = Path(storage_path).name

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

        return file_record

    def download_file(
        self,
        file_id: UUID,
    ) -> tuple[bytes, str, str]:
        file_record = self.file_repository.get_by_id(file_id)

        if not file_record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found.",
            )

        if not self.storage.exists(file_record.storage_path):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Stored file not found.",
            )

        content = self.storage.read(
            file_record.storage_path,
        )

        return (
            content,
            file_record.original_filename,
            file_record.content_type,
        )

    def delete_file(
        self,
        file_id: UUID,
    ) -> None:
        file_record = self.file_repository.get_by_id(file_id)

        if not file_record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found.",
            )

        self.storage.delete(
            file_record.storage_path,
        )

        self.file_repository.delete(file_record)
