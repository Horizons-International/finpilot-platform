from datetime import datetime
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
)

from app.schemas.mixins import (
    EmailFieldValidatorMixin,
    NameFieldValidatorMixin,
    PhoneFieldValidatorMixin,
)
from app.utils.enums import UserRole, UserStatus


class UserCreate(NameFieldValidatorMixin, EmailFieldValidatorMixin, BaseModel):
    first_name: str = Field(
        min_length=1,
        max_length=100,
    )
    last_name: str = Field(
        min_length=1,
        max_length=100,
    )
    email: EmailStr
    password: str = Field(
        min_length=8,
        max_length=128,
    )
    role: UserRole


class UserUpdate(NameFieldValidatorMixin, EmailFieldValidatorMixin, BaseModel):
    first_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )
    last_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )
    email: EmailStr | None = None
    role: UserRole | None = None


class UserStatusUpdate(BaseModel):
    status: UserStatus


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    first_name: str
    last_name: str
    email: EmailStr
    status: UserStatus
    role: UserRole
    is_deleted: bool
    created_at: datetime
    updated_at: datetime


class UserListResponse(BaseModel):
    users: list[UserResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class ProfileUpdateRequest(
    NameFieldValidatorMixin, PhoneFieldValidatorMixin, BaseModel
):
    first_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )

    last_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )

    phone_number: str | None = Field(
        default=None,
        max_length=30,
    )


class ProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    first_name: str
    last_name: str
    email: EmailStr
    phone_number: str | None
    status: UserStatus
    role: UserRole
