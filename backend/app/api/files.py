from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, UploadFile, status
from fastapi import File as FastAPIFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.responses import APIResponse
from app.core.security import get_current_user, require_roles
from app.schemas.file import FileResponse
from app.services.file_service import FileService
from app.storages.local_storage import LocalStorage
from app.utils.enums import UserRole

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
    summary="Upload a file",
    description="Upload a file to the storage service.",
)
async def upload_file(
    file: UploadFile = FastAPIFile(...),
    module: str = "customers",
    folder: str = "uploads",
    current_user: dict[str, Any] = Depends(get_current_user),
    service: FileService = Depends(get_file_service),
):
    file_record = await service.upload_file(
        file=file,
        uploaded_by=UUID(current_user["sub"]),
        email=current_user["email"],
        module=module,
        folder=folder,
    )

    return APIResponse(
        success=True,
        message="File uploaded successfully.",
        data=FileResponse.model_validate(file_record),
    )


@router.get(
    "/{file_id}",
    summary="Get file",
    description="Retrieve an file from the storage service by ID.",
)
def download_file(
    file_id: UUID,
    service: FileService = Depends(get_file_service),
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            resource_type="file",
        )
    ),
):
    content, filename, content_type = service.download_file(
        file_id=file_id,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
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
    summary="Delete a file",
    description="Delete a file from storage services by ID.",
)
def delete_file(
    file_id: UUID,
    service: FileService = Depends(get_file_service),
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            resource_type="file",
        )
    ),
):
    service.delete_file(
        file_id=file_id,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
    )

    return APIResponse(
        success=True,
        message="File deleted successfully.",
        data=None,
    )
