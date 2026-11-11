from typing import Any

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.async_security import get_async_current_user, require_async_roles
from app.core.database import get_async_db
from app.core.dependencies import get_user_invitation_service
from app.core.responses import APIResponse
from app.models.user import User
from app.schemas.auth import (
    AcceptInvitationRequest,
    ChangePasswordRequest,
    LoginRequest,
    LoginResponse,
    RefreshTokenRequest,
    RefreshTokenResponse,
)
from app.services.async_auth_service import AsyncAuthService
from app.services.user_invitation_service import UserInvitationService
from app.utils.enums import UserRole

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])


@router.post(
    "/login",
    response_model=APIResponse[LoginResponse],
    status_code=status.HTTP_200_OK,
    summary="Authenticate user",
    description="Authenticates a user and returns access and refresh tokens.",
)
async def login(
    login_data: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
) -> APIResponse[LoginResponse]:
    result = await AsyncAuthService(db).login(
        email=login_data.email,
        password=login_data.password,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        mfa_code=login_data.mfa_code,
    )
    return APIResponse(success=True, message="Login successful.", data=result)


@router.post(
    "/refresh",
    response_model=APIResponse[RefreshTokenResponse],
    status_code=status.HTTP_200_OK,
    summary="Refresh access token",
    description="Generates a new access token using a valid refresh token.",
)
async def refresh_token(
    refresh_data: RefreshTokenRequest,
    db: AsyncSession = Depends(get_async_db),
) -> APIResponse[RefreshTokenResponse]:
    result = await AsyncAuthService(db).refresh_token(refresh_data.refresh_token)
    return APIResponse(
        success=True,
        message="Access token refreshed successfully.",
        data=result,
    )


@router.get(
    "/admin-only",
    response_model=APIResponse,
    status_code=status.HTTP_200_OK,
    summary="For administrators",
    description=(
        "Endpoint to test administrator authentication. "
        "Only administrators can access this endpoint."
    ),
)
async def admin_only(
    current_user: dict[str, Any] = Depends(
        require_async_roles(UserRole.ADMINISTRATOR, resource_type="Admin_only")
    ),
) -> APIResponse[Any]:
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
async def change_password(
    password_data: ChangePasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_async_current_user),
) -> APIResponse[dict[str, str]]:
    await AsyncAuthService(db).change_password(
        user_id=current_user.id,
        password_data=password_data,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return APIResponse(
        success=True,
        message="Password changed successfully.",
        data={"message": "Password changed successfully."},
    )


# Invitation acceptance is intentionally left on its existing synchronous
# service because its repository and onboarding transaction have not yet been
# migrated to AsyncSession.
@router.post(
    "/accept-invitation",
    response_model=APIResponse[dict[str, str]],
    status_code=status.HTTP_201_CREATED,
    summary="Accept user invitation",
)
def accept_invitation(
    payload: AcceptInvitationRequest,
    service: UserInvitationService = Depends(get_user_invitation_service),
) -> APIResponse[dict[str, str]]:
    user = service.accept(token=payload.token, password=payload.password)
    return APIResponse(
        success=True,
        message="Invitation accepted successfully.",
        data={"user_id": str(user.id), "email": user.email},
    )
