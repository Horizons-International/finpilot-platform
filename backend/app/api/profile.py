from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.responses import APIResponse
from app.core.security import get_current_user
from app.repositories.user_repository import UserRepository
from app.schemas.user import ProfileResponse, ProfileUpdateRequest

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
    user_repository = UserRepository(db)

    user = user_repository.get_by_id(
        current_user["sub"],
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
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
    user_repository = UserRepository(db)

    user = user_repository.get_by_id(current_user["sub"])

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    user.first_name = profile_data.first_name
    user.last_name = profile_data.last_name
    user.phone_number = profile_data.phone_number

    user_repository.update(user)

    return APIResponse(
        success=True,
        message="Profile updated successfully.",
        data=ProfileResponse.model_validate(user),
    )
