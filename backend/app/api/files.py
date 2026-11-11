from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, UploadFile, status
from fastapi import File as FastAPIFile
from fastapi.responses import Response

from app.core.async_dependencies import get_async_file_service
from app.core.async_security import require_async_roles
from app.core.responses import APIResponse
from app.schemas.file import FileResponse
from app.services.async_file_service import AsyncFileService
from app.utils.enums import UserRole

router = APIRouter(prefix="/api/v1/files", tags=["Files"])


@router.post(
    "",
    response_model=APIResponse[FileResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Upload a file",
    description="Upload a file to the storage service.",
)
async def upload_file(
    request: Request,
    file: UploadFile = FastAPIFile(...),
    module: str = "customers",
    folder: str = "uploads",
    current_user: dict[str, Any] = Depends(
        require_async_roles(UserRole.ADMINISTRATOR, resource_type="file")
    ),
    service: AsyncFileService = Depends(get_async_file_service),
) -> APIResponse[FileResponse]:
    file_record = await service.upload_file(
        file=file,
        uploaded_by=UUID(current_user["sub"]),
        email=current_user["email"],
        module=module,
        folder=folder,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return APIResponse(
        success=True,
        message="File uploaded successfully.",
        data=FileResponse.model_validate(file_record),
    )


@router.get(
    "/{file_id}",
    status_code=status.HTTP_200_OK,
    summary="Get file",
    description="Retrieve a file from the storage service by ID.",
)
async def download_file(
    request: Request,
    file_id: UUID,
    service: AsyncFileService = Depends(get_async_file_service),
    current_user: dict[str, Any] = Depends(
        require_async_roles(UserRole.ADMINISTRATOR, resource_type="file")
    ),
) -> Response:
    content, filename, content_type = await service.download_file(
        file_id=file_id,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return Response(
        content=content,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete(
    "/{file_id}",
    response_model=APIResponse[None],
    status_code=status.HTTP_200_OK,
    summary="Delete a file",
    description="Delete a file from storage services by ID.",
)
async def delete_file(
    request: Request,
    file_id: UUID,
    service: AsyncFileService = Depends(get_async_file_service),
    current_user: dict[str, Any] = Depends(
        require_async_roles(UserRole.ADMINISTRATOR, resource_type="file")
    ),
) -> APIResponse[None]:
    await service.delete_file(
        file_id=file_id,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return APIResponse(
        success=True,
        message="File deleted successfully.",
        data=None,
    )
