from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr

from app.models.user import UserStatus


class UserCreate(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    password: str
    role: str


class UserUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    email: EmailStr | None = None
    role: str | None = None


class UserStatusUpdate(BaseModel):
    status: UserStatus


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    first_name: str
    last_name: str
    email: EmailStr
    status: UserStatus
    role: str
    is_deleted: bool
    created_at: datetime
    updated_at: datetime


class UserListResponse(BaseModel):
    users: list[UserResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
