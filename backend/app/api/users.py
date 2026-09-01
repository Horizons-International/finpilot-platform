from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.responses import APIResponse
from app.core.security import (
    Roles,
    require_roles,
)
from app.schemas.user import (
    UserCreate,
    UserListResponse,
    UserResponse,
    UserStatusUpdate,
    UserUpdate,
)
from app.services.user_service import UserService

router = APIRouter(
    prefix="/api/v1/users",
    tags=["Users"],
)


@router.post(
    "",
    response_model=APIResponse[UserResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create user",
    description="Creates a new user account.",
)
def create_user(
    user_data: UserCreate,
    db: Session = Depends(get_db),
    _: dict = Depends(require_roles(Roles.ADMINISTRATOR)),
):
    service = UserService(db)

    user = service.create_user(user_data)

    return APIResponse(
        success=True,
        message="User created successfully.",
        data=UserResponse.model_validate(user),
    )


@router.get(
    "/{user_id}",
    response_model=APIResponse[UserResponse],
    summary="Get user",
    description="Retrieves a user by ID.",
)
def get_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    _: dict = Depends(require_roles(Roles.ADMINISTRATOR)),
):
    service = UserService(db)

    user = service.get_user(user_id)

    return APIResponse(
        success=True,
        message="User retrieved successfully.",
        data=UserResponse.model_validate(user),
    )


@router.get(
    "",
    response_model=APIResponse[UserListResponse],
    summary="Get users",
    description="Retrieves all the users in the database.",
)
def get_users(
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    _: dict = Depends(require_roles(Roles.ADMINISTRATOR)),
):
    service = UserService(db)

    user_list = service.get_users(
        page,
        page_size,
    )

    return APIResponse(
        success=True,
        message="Users retrieved successfully.",
        data=user_list,
    )


@router.put(
    "/{user_id}",
    response_model=APIResponse[UserResponse],
    summary="Update user",
    description="Updates an existing user information.",
)
def update_user(
    user_id: UUID,
    user_data: UserUpdate,
    db: Session = Depends(get_db),
    _: dict = Depends(require_roles(Roles.ADMINISTRATOR)),
):
    service = UserService(db)

    user = service.update_user(
        user_id,
        user_data,
    )

    return APIResponse(
        success=True,
        message="User updated successfully.",
        data=UserResponse.model_validate(user),
    )


@router.patch(
    "/{user_id}/status",
    response_model=APIResponse[UserResponse],
    summary="Update user status",
    description="Updates the status of an existing user.",
)
def update_user_status(
    user_id: UUID,
    status_data: UserStatusUpdate,
    db: Session = Depends(get_db),
    _: dict = Depends(require_roles(Roles.ADMINISTRATOR)),
):
    service = UserService(db)

    user = service.update_status(
        user_id,
        status_data,
    )

    return APIResponse(
        success=True,
        message="User status updated successfully.",
        data=UserResponse.model_validate(user),
    )


@router.delete(
    "/{user_id}",
    response_model=APIResponse[UserResponse],
    summary="Delete user",
    description="Delete an existing user by ID",
)
def delete_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    _: dict = Depends(require_roles(Roles.ADMINISTRATOR)),
):
    service = UserService(db)

    user = service.delete_user(user_id)

    return APIResponse(
        success=True,
        message="User deleted successfully.",
        data=UserResponse.model_validate(user),
    )
