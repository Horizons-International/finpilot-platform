from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.responses import APIResponse
from app.core.security import get_current_user
from app.schemas.user import ProfileResponse, ProfileUpdateRequest
from app.services.profile_service import ProfileService

router = APIRouter(
    prefix="/api/v1/profile",
    tags=["Profile"],
)


@router.get(
    "",
    response_model=APIResponse[ProfileResponse],
)
def get_profile(
    current_user: dict[str, Any] = Depends(get_current_user),
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
)
def update_profile(
    profile_data: ProfileUpdateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = ProfileService(db)

    user = service.update_profile(
        UUID(current_user["sub"]),
        profile_data,
    )

    return APIResponse(
        success=True,
        message="Profile updated successfully.",
        data=ProfileResponse.model_validate(user),
    )
