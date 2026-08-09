from pydantic import BaseModel, ConfigDict, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "email": "admin@example.com",
                "password": "Password12345",
            }
        }
    )


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id: str
    first_name: str
    last_name: str
    email: EmailStr
    status: str
    role: str


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    user: UserResponse


class RefreshTokenResponse(BaseModel):
    access_token: str
    token_type: str
