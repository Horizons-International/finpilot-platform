from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import ProfileUpdateRequest


class ProfileService:
    def __init__(self, db: Session):
        self.repository = UserRepository(db)

    def get_profile(self, user_id: Any) -> User:
        user = self.repository.get_by_id(user_id)

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        return user

    def update_profile(
        self,
        user_id: Any,
        profile_data: ProfileUpdateRequest,
    ) -> User:
        user = self.get_profile(user_id)

        user.first_name = profile_data.first_name
        user.last_name = profile_data.last_name
        user.phone_number = profile_data.phone_number

        return self.repository.update(user)
