from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.schemas.mixins import EmailFieldValidatorMixin
from app.utils.enums import UserRole, UserStatus


class LoginRequest(EmailFieldValidatorMixin, BaseModel):
    email: EmailStr
    password: str = Field(
        min_length=8,
        max_length=128,
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "email": "admin@example.com",
                "password": "StrongPassword123*",
            }
        }
    )


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class AuthUserResponse(BaseModel):
    id: str
    first_name: str
    last_name: str
    email: EmailStr
    status: UserStatus
    role: UserRole
    tenant_id: str
    tenant_code: str


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    user: AuthUserResponse


class RefreshTokenResponse(BaseModel):
    access_token: str
    token_type: str


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(
        min_length=8,
        max_length=128,
    )
    new_password: str = Field(
        min_length=8,
        max_length=128,
    )


class MeResponse(BaseModel):
    id: str
    first_name: str
    last_name: str
    email: EmailStr
    role: UserRole


class AcceptInvitationRequest(BaseModel):
    token: str = Field(
        min_length=1,
    )

    password: str = Field(
        min_length=8,
        max_length=128,
    )
