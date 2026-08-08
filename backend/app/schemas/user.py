from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr

from app.models.user import UserStatus


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    first_name: str
    last_name: str
    email: EmailStr
    status: UserStatus
    role: str
    created_at: str
    updated_at: str
