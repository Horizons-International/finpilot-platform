from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.user import UserRole, UserStatus


class LoginRequest(BaseModel):
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
