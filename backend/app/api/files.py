from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, UploadFile, status
from fastapi import File as FastAPIFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.responses import APIResponse
from app.core.security import Roles, get_current_user, require_roles
from app.schemas.file import FileResponse
from app.services.file_service import FileService
from app.storage.local_storage import LocalStorage

router = APIRouter(
    prefix="/api/v1/files",
    tags=["Files"],
)


def get_file_service(
    db: Session = Depends(get_db),
) -> FileService:
    storage = LocalStorage(
        settings.STORAGE_PATH,
    )

    return FileService(
        db=db,
        storage=storage,
    )


@router.post(
    "",
    response_model=APIResponse[FileResponse],
    status_code=status.HTTP_201_CREATED,
)
async def upload_file(
    file: UploadFile = FastAPIFile(...),
    module: str = "customers",
    folder: str = "uploads",
    current_user: dict = Depends(get_current_user),
    service: FileService = Depends(get_file_service),
):
    file_record = await service.upload_file(
        file=file,
        uploaded_by=UUID(current_user["sub"]),
        module=module,
        folder=folder,
    )

    return APIResponse(
        success=True,
        message="File uploaded successfully.",
        data=FileResponse.model_validate(file_record),
    )


@router.get("/{file_id}")
def download_file(
    file_id: UUID,
    service: FileService = Depends(get_file_service),
):
    content, filename, content_type = service.download_file(
        file_id,
    )

    return Response(
        content=content,
        media_type=content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@router.delete(
    "/{file_id}",
    response_model=APIResponse[None],
)
def delete_file(
    file_id: UUID,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(require_roles(Roles.ADMINISTRATOR)),
):
    storage = LocalStorage(settings.STORAGE_PATH)

    file_service = FileService(
        db=db,
        storage=storage,
    )

    file_service.delete_file(file_id)

    return APIResponse(
        success=True,
        message="File deleted successfully.",
        data=None,
    )
