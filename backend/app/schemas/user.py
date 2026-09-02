from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.user import UserRole, UserStatus
from app.utils.strings import normalize_email as nonormalize_email_value
from app.utils.strings import normalize_whitespace


class UserCreate(BaseModel):
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

    @field_validator(
        "first_name",
        "last_name",
        mode="before",
    )
    @classmethod
    def normalize_names(cls, value: str) -> str:
        return normalize_whitespace(value)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> EmailStr:
        return nonormalize_email_value(value)


class UserUpdate(BaseModel):
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

    @field_validator(
        "first_name",
        "last_name",
        mode="before",
    )
    @classmethod
    def normalize_names(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalize_whitespace(value)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr | None) -> EmailStr | None:
        if value is None:
            return None
        return nonormalize_email_value(value)


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


class ProfileUpdateRequest(BaseModel):
    first_name: str = Field(
        min_length=1,
        max_length=100,
    )

    last_name: str = Field(
        min_length=1,
        max_length=100,
    )

    phone_number: str | None = Field(
        default=None,
        max_length=30,
    )

    @field_validator("first_name", "last_name")
    @classmethod
    def normalize_names(cls, value: str) -> str:
        return normalize_whitespace(value)


class ProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    first_name: str
    last_name: str
    email: EmailStr
    phone_number: str | None
    status: UserStatus
    role: UserRole
