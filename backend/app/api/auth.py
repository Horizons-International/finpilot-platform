from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.responses import APIResponse
from app.core.security import (
    Roles,
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    get_current_user,
    hash_password,
    require_roles,
    validate_password,
    verify_password,
)
from app.models.audit_log import AuditEventType
from app.models.user import User, UserStatus
from app.schemas.auth import (
    AuthUserResponse,
    ChangePasswordRequest,
    LoginRequest,
    LoginResponse,
    RefreshTokenRequest,
    RefreshTokenResponse,
)
from app.services.audit import log_auth_event

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
    user = db.query(User).filter(User.email == login_data.email).first()

    if not user:
        log_auth_event(
            db=db,
            event_type=AuditEventType.LOGIN_FAILURE,
            email=login_data.email,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not verify_password(
        login_data.password,
        user.password_hash,
    ):
        log_auth_event(
            db=db,
            event_type=AuditEventType.LOGIN_FAILURE,
            user_id=user.id,
            email=user.email,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if user.status == UserStatus.INACTIVE:
        log_auth_event(
            db=db,
            event_type=AuditEventType.LOGIN_FAILURE,
            user_id=user.id,
            email=user.email,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )

    if user.status == UserStatus.LOCKED:
        log_auth_event(
            db=db,
            event_type=AuditEventType.LOGIN_FAILURE,
            user_id=user.id,
            email=user.email,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is locked",
        )

    token_data = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role,
    }

    access_token = create_access_token(
        data=token_data,
    )

    refresh_token = create_refresh_token(
        data=token_data,
    )

    log_auth_event(
        db=db,
        event_type=AuditEventType.LOGIN_SUCCESS,
        user_id=user.id,
        email=user.email,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return APIResponse(
        success=True,
        message="Login successful.",
        data=LoginResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            user=AuthUserResponse(
                id=str(user.id),
                first_name=user.first_name,
                last_name=user.last_name,
                email=user.email,
                status=user.status.value,
                role=user.role,
            ),
        ),
    )


@router.post(
    "/refresh",
    response_model=APIResponse[RefreshTokenResponse],
)
def refresh_token(
    refresh_data: RefreshTokenRequest,
):
    try:
        payload = decode_refresh_token(
            refresh_data.refresh_token,
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    user_id = payload.get("sub")

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    access_token = create_access_token(
        data={
            "sub": user_id,
            "email": payload.get("email"),
            "role": payload.get("role"),
        }
    )

    return APIResponse(
        success=True,
        message="Access token refreshed successfully.",
        data=RefreshTokenResponse(
            access_token=access_token,
            token_type="bearer",
        ),
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
    user = db.query(User).filter(User.id == current_user["sub"]).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if not verify_password(
        password_data.current_password,
        user.password_hash,
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    if password_data.current_password == password_data.new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be different from current password",
        )

    try:
        validate_password(password_data.new_password)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    user.password_hash = hash_password(password_data.new_password)

    db.commit()

    log_auth_event(
        db=db,
        event_type=AuditEventType.PASSWORD_CHANGE,
        user_id=user.id,
        email=user.email,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return APIResponse(
        success=True,
        message="Password changed successfully.",
        data={"message": "Password changed successfully."},
    )
