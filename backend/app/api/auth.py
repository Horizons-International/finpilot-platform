from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.responses import APIResponse
from app.core.security import (
    Roles,
    get_current_user,
    require_roles,
)
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    LoginResponse,
    RefreshTokenRequest,
    RefreshTokenResponse,
)
from app.services.auth_services import AuthService

router = APIRouter(
    prefix="/api/v1/auth",
    tags=["Authentication"],
)


@router.post(
    "/login",
    response_model=APIResponse[LoginResponse],
)
def login(
    login_data: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
):
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
)
def admin_only(
    current_user: dict[str, Any] = Depends(require_roles(Roles.ADMINISTRATOR)),
):
    return APIResponse(
        success=True,
        message="Administrator access granted",
        data={"user_id": current_user["sub"]},
    )


@router.post(
    "/change-password",
    response_model=APIResponse[dict[str, str]],
)
def change_password(
    password_data: ChangePasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_current_user),
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
