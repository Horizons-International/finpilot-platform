from typing import Any

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_user_invitation_service
from app.core.responses import APIResponse
from app.core.security import (
    get_current_user,
    require_roles,
)
from app.models.user import User
from app.schemas.auth import (
    AcceptInvitationRequest,
    ChangePasswordRequest,
    LoginRequest,
    LoginResponse,
    RefreshTokenRequest,
    RefreshTokenResponse,
)
from app.services.auth_service import AuthService
from app.services.user_invitation_service import (
    UserInvitationService,
)
from app.utils.enums import UserRole

router = APIRouter(
    prefix="/api/v1/auth",
    tags=["Authentication"],
)


@router.post(
    "/login",
    response_model=APIResponse[LoginResponse],
    status_code=status.HTTP_200_OK,
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
    status_code=status.HTTP_200_OK,
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
    response_model=APIResponse,
    status_code=status.HTTP_200_OK,
    summary="For administrators",
    description=(
        "Endpoint to test out administrator authentication."
        "Only administrators are able to use this endpoint."
    ),
)
def admin_only(
    current_user: dict[str, Any] = Depends(
        require_roles(UserRole.ADMINISTRATOR, resource_type="Admin_only"),
    ),
):
    return APIResponse(
        success=True,
        message="Administrator access granted",
        data={"user_id": current_user["sub"]},
    )


@router.post(
    "/change-password",
    response_model=APIResponse[dict[str, str]],
    status_code=status.HTTP_200_OK,
    summary="Change password",
    description="Changes the password of the currently authenticated user.",
)
def change_password(
    password_data: ChangePasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = AuthService(db)

    service.change_password(
        user_id=current_user.id,
        password_data=password_data,
        ip_address=(request.client.host if request.client else None),
        user_agent=request.headers.get("user-agent"),
    )

    return APIResponse(
        success=True,
        message="Password changed successfully.",
        data={"message": "Password changed successfully."},
    )


@router.post(
    "/accept-invitation",
    response_model=APIResponse[dict[str, str]],
    status_code=status.HTTP_201_CREATED,
    summary="Accept user invitation",
)
def accept_invitation(
    payload: AcceptInvitationRequest,
    service: UserInvitationService = Depends(
        get_user_invitation_service,
    ),
) -> APIResponse[dict[str, str]]:
    user = service.accept(
        token=payload.token,
        password=payload.password,
    )

    return APIResponse(
        success=True,
        message="Invitation accepted successfully.",
        data={
            "user_id": str(user.id),
            "email": user.email,
        },
    )
