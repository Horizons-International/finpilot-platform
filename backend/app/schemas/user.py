from datetime import datetime
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    ValidationInfo,
    field_validator,
)

from app.utils.enums import UserRole, UserStatus
from app.utils.validators import validate_email, validate_name, validate_phone


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
    def validate_names(
        cls,
        value: str,
        info: ValidationInfo,
    ) -> str:
        field_name = info.field_name

        if field_name is None:
            field_name = "Name"

        field_name = field_name.replace("_", " ").title()
        return validate_name(value, field_name=field_name)

    @field_validator("email", mode="before")
    @classmethod
    def validate_email_address(cls, value: str) -> str:
        return validate_email(value)


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
    def normalize_names(
        cls,
        value: str | None,
        info: ValidationInfo,
    ) -> str | None:
        if value is None:
            return None
        field_name = info.field_name

        if field_name is None:
            field_name = "Name"

        field_name = field_name.replace("_", " ").title()
        return validate_name(value, field_name=field_name)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_email(value)


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

    @field_validator(
        "first_name",
        "last_name",
        mode="before",
    )
    @classmethod
    def normalize_names(
        cls,
        value: str,
        info: ValidationInfo,
    ) -> str:
        field_name = info.field_name

        if field_name is None:
            field_name = "Name"

        field_name = field_name.replace("_", " ").title()
        return validate_name(value, field_name=field_name)

    @field_validator("phone_number", mode="before")
    @classmethod
    def validate_phone_number(cls, value: str | None) -> str | None:
        if value is None:
            return None

        return validate_phone(value)


class ProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    first_name: str
    last_name: str
    email: EmailStr
    phone_number: str | None
    status: UserStatus
    role: UserRole
