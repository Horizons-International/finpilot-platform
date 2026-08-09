from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import (
    Roles,
    hash_password,
    require_roles,
)
from app.models.user import User, UserStatus
from app.schemas.user import (
    UserCreate,
    UserListResponse,
    UserResponse,
    UserStatusUpdate,
    UserUpdate,
)

router = APIRouter(
    prefix="/api/v1/users",
    tags=["Users"],
)


@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_user(
    user_data: UserCreate,
    db: Session = Depends(get_db),
    _: dict = Depends(require_roles(Roles.ADMINISTRATOR)),
):
    existing_user = db.query(User).filter(User.email == user_data.email).first()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is already registered",
        )

    user = User(
        first_name=user_data.first_name,
        last_name=user_data.last_name,
        email=user_data.email,
        password_hash=hash_password(user_data.password),
        status=UserStatus.ACTIVE,
        role=user_data.role,
        is_deleted=False,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user


@router.get(
    "/{user_id}",
    response_model=UserResponse,
)
def get_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    _: dict = Depends(require_roles(Roles.ADMINISTRATOR)),
):
    user = (
        db.query(User)
        .filter(
            User.id == user_id,
            User.is_deleted.is_(False),
        )
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    return user


@router.get(
    "",
    response_model=UserListResponse,
)
def get_users(
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    _: dict = Depends(require_roles(Roles.ADMINISTRATOR)),
):
    if page < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Page must be greater than or equal to 1",
        )

    if page_size < 1 or page_size > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Page size must be between 1 and 100",
        )

    query = db.query(User).filter(User.is_deleted.is_(False))

    total = query.count()

    offset = (page - 1) * page_size

    users = query.offset(offset).limit(page_size).all()

    total_pages = (total + page_size - 1) // page_size if total > 0 else 0

    user_responses = [UserResponse.model_validate(user) for user in users]

    return UserListResponse(
        users=user_responses,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.put(
    "/{user_id}",
    response_model=UserResponse,
)
def update_user(
    user_id: UUID,
    user_data: UserUpdate,
    db: Session = Depends(get_db),
    _: dict = Depends(require_roles(Roles.ADMINISTRATOR)),
):
    user = (
        db.query(User)
        .filter(
            User.id == user_id,
            User.is_deleted.is_(False),
        )
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if user_data.email is not None:
        existing_user = (
            db.query(User)
            .filter(
                User.email == user_data.email,
                User.id != user_id,
                User.is_deleted.is_(False),
            )
            .first()
        )

        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email is already registered",
            )

        user.email = user_data.email

    if user_data.first_name is not None:
        user.first_name = user_data.first_name

    if user_data.last_name is not None:
        user.last_name = user_data.last_name

    if user_data.role is not None:
        user.role = user_data.role

    db.commit()
    db.refresh(user)

    return user


@router.patch(
    "/{user_id}/status",
    response_model=UserResponse,
)
def update_user_status(
    user_id: UUID,
    status_data: UserStatusUpdate,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(require_roles(Roles.ADMINISTRATOR)),
):
    user = (
        db.query(User)
        .filter(
            User.id == user_id,
            User.is_deleted.is_(False),
        )
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    user.status = status_data.status

    db.commit()
    db.refresh(user)

    return user


@router.delete(
    "/{user_id}",
    response_model=UserResponse,
)
def delete_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(require_roles(Roles.ADMINISTRATOR)),
):
    user = (
        db.query(User)
        .filter(
            User.id == user_id,
            User.is_deleted.is_(False),
        )
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    user.is_deleted = True
    user.status = UserStatus.INACTIVE

    db.commit()
    db.refresh(user)

    return user
