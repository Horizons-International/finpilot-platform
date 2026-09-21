from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.responses import APIResponse
from app.core.security import get_current_user_payload
from app.schemas.user import ProfileResponse, ProfileUpdateRequest
from app.services.profile_service import ProfileService

router = APIRouter(
    prefix="/api/v1/profile",
    tags=["Profile"],
)


@router.get(
    "",
    response_model=APIResponse[ProfileResponse],
    status_code=status.HTTP_200_OK,
    summary="Get profile",
    description="Retreive information the current user account.",
)
def get_profile(
    current_user: dict[str, Any] = Depends(get_current_user_payload),
    db: Session = Depends(get_db),
):
    service = ProfileService(db)

    user = service.get_profile(
        UUID(current_user["sub"]),
    )

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
    description="Updates the information of the current user.",
)
def update_profile(
    request: Request,
    profile_data: ProfileUpdateRequest,
    current_user: dict[str, Any] = Depends(get_current_user_payload),
    db: Session = Depends(get_db),
):
    service = ProfileService(db)

    user = service.update_profile(
        UUID(current_user["sub"]),
        profile_data,
        ip_address=(request.client.host if request.client else None),
        user_agent=request.headers.get("user-agent"),
    )

    return APIResponse(
        success=True,
        message="Profile updated successfully.",
        data=ProfileResponse.model_validate(user),
    )
