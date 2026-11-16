"""Profile endpoints backed by native async SQLAlchemy sessions."""

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.async_security import get_async_current_user
from app.core.database import get_async_db
from app.core.responses import APIResponse
from app.models.user import User
from app.schemas.user import ProfileResponse, ProfileUpdateRequest
from app.services.async_profile_service import AsyncProfileService

router = APIRouter(
    prefix="/api/v1/profile",
    tags=["Profile"],
)


def _service(db: AsyncSession, current_user: User) -> AsyncProfileService:
    return AsyncProfileService(db, current_user.tenant_id)


@router.get(
    "",
    response_model=APIResponse[ProfileResponse],
    status_code=status.HTTP_200_OK,
    summary="Get profile",
    description="Retrieve information about the current user account.",
)
async def get_profile(
    current_user: User = Depends(get_async_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> APIResponse[ProfileResponse]:
    user = await _service(db, current_user).get_profile(current_user.id)
    return APIResponse(
        success=True,
        message="Profile retrieved successfully.",
        data=ProfileResponse.model_validate(user),
    )


@router.put(
    "",
    response_model=APIResponse[ProfileResponse],
    status_code=status.HTTP_200_OK,
    summary="Update profile",
    description="Update the information of the current user.",
)
async def update_profile(
    request: Request,
    profile_data: ProfileUpdateRequest,
    current_user: User = Depends(get_async_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> APIResponse[ProfileResponse]:
    user = await _service(db, current_user).update_profile(
        current_user.id,
        profile_data,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return APIResponse(
        success=True,
        message="Profile updated successfully.",
        data=ProfileResponse.model_validate(user),
    )
