from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.audit_log import AuditEventType
from app.models.user import User, UserStatus
from app.repositories.user_repository import UserRepository
from app.schemas.user import (
    UserCreate,
    UserListResponse,
    UserResponse,
    UserStatusUpdate,
    UserUpdate,
)
from app.services.audit_service import AuditService


class UserService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = UserRepository(db)
        self.audit_service = AuditService(db)

    def create_user(self, user_data: UserCreate) -> User:
        existing_user = self.repository.get_by_email(
            user_data.email,
        )

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

        user = self.repository.create(user)

        # Make sure the generated user ID is available
        self.db.flush()

        self.audit_service.log_event(
            event_type=AuditEventType.USER_CREATED,
            user_id=user.id,
            email=user.email,
            resource_type="user",
            resource_id=user.id,
        )

        self.db.commit()
        self.db.refresh(user)

        return user

    def get_user(self, user_id: UUID) -> User:
        user = self.repository.get_by_id(user_id)

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        return user

    def update_user(
        self,
        user_id: UUID,
        user_data: UserUpdate,
    ) -> User:
        user = self.get_user(user_id)

        if user_data.email is not None:
            existing_user = self.repository.get_by_email(
                user_data.email,
            )

            if existing_user and existing_user.id != user_id:
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

        user = self.repository.update(user)

        self.audit_service.log_event(
            event_type=AuditEventType.USER_UPDATED,
            user_id=user.id,
            email=user.email,
            resource_type="user",
            resource_id=user.id,
        )

        self.db.commit()
        self.db.refresh(user)

        return user

    def update_status(
        self,
        user_id: UUID,
        status_data: UserStatusUpdate,
    ) -> User:
        user = self.get_user(user_id)

        user.status = status_data.status

        user = self.repository.update(user)

        self.audit_service.log_event(
            event_type=AuditEventType.USER_STATUS_CHANGED,
            user_id=user.id,
            email=user.email,
            resource_type="user",
            resource_id=user.id,
        )

        self.db.commit()
        self.db.refresh(user)

        return user

    def delete_user(self, user_id: UUID) -> User:
        user = self.get_user(user_id)

        self.repository.soft_delete(user)

        self.audit_service.log_event(
            event_type=AuditEventType.USER_DELETED,
            user_id=user.id,
            email=user.email,
            resource_type="user",
            resource_id=user.id,
        )

        self.db.commit()
        self.db.refresh(user)

        return user

    def get_users(
        self,
        page: int = 1,
        page_size: int = 20,
    ) -> UserListResponse:
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

        users, total = self.repository.get_paginated(
            page=page,
            page_size=page_size,
        )

        user_responses = [UserResponse.model_validate(user) for user in users]

        total_pages = (total + page_size - 1) // page_size if total > 0 else 0

        return UserListResponse(
            users=user_responses,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )
