from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.responses import APIResponse
from app.core.security import get_current_user_payload, require_roles
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    LoginResponse,
    RefreshTokenRequest,
    RefreshTokenResponse,
)
from app.services.auth_service import AuthService
from app.utils.enums import UserRole

router = APIRouter(
    prefix="/api/v1/auth",
    tags=["Authentication"],
)


@router.post(
    "/login",
    response_model=APIResponse[LoginResponse],
    summary="Authenticate user",
    description="Authenticates a user and returns access and refresh tokens.",
)
def login(
    login_data: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> APIResponse[LoginResponse]:
    service = AuthService(db)

    result = service.login(
        email=login_data.email,
        password=login_data.password,
        ip_address=(request.client.host if request.client else None),
        user_agent=request.headers.get("user-agent"),
    )

    return APIResponse(success=True, message="Login successful.", data=result)


@router.post(
    "/refresh",
    response_model=APIResponse[RefreshTokenResponse],
    summary="Refresh access token",
    description="Generates a new access token using a valid refresh token.",
)
def refresh_token(
    refresh_data: RefreshTokenRequest,
    db: Session = Depends(get_db),
):
    service = AuthService(db)

    result = service.refresh_token(refresh_token=refresh_data.refresh_token)

    return APIResponse(
        success=True, message="Access token refreshed successfully.", data=result
    )


@router.get(
    "/admin-only",
    summary="For administrators",
    description=(
        "Endpoint to test out administrator authentication."
        "Only administrators are able to use this endpoint."
    ),
)
def admin_only(
    current_user: dict[str, Any] = Depends(require_roles(UserRole.ADMINISTRATOR)),
):
    return APIResponse(
        success=True,
        message="Administrator access granted",
        data={"user_id": current_user["sub"]},
    )


@router.post(
    "/change-password",
    response_model=APIResponse[dict[str, str]],
    summary="Change password",
    description="Changes the password of the currently authenticated user.",
)
def change_password(
    password_data: ChangePasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_current_user_payload),
):
    service = AuthService(db)

    service.change_password(
        user_id=UUID(current_user["sub"]),
        password_data=password_data,
        ip_address=(request.client.host if request.client else None),
        user_agent=request.headers.get("user-agent"),
    )

    return APIResponse(
        success=True,
        message="Password changed successfully.",
        data={"message": "Password changed successfully."},
    )
