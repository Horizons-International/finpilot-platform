from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import (
    Roles,
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    require_roles,
    verify_password,
)
from app.models.user import User, UserStatus
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    RefreshTokenRequest,
    RefreshTokenResponse,
    UserResponse,
)

router = APIRouter(
    prefix="/api/v1/auth",
    tags=["Authentication"],
)


@router.post(
    "/login",
    response_model=LoginResponse,
)
def login(
    login_data: LoginRequest,
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == login_data.email).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not verify_password(
        login_data.password,
        user.password_hash,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if user.status != UserStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is not active",
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

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        user=UserResponse(
            id=str(user.id),
            first_name=user.first_name,
            last_name=user.last_name,
            email=user.email,
            status=user.status.value,
            role=user.role,
        ),
    )


@router.post(
    "/refresh",
    response_model=RefreshTokenResponse,
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

    return RefreshTokenResponse(
        access_token=access_token,
        token_type="bearer",
    )


@router.get(
    "/admin-only",
)
def admin_only(
    current_user: dict[str, Any] = Depends(require_roles(Roles.ADMINISTRATOR)),
):
    return {
        "message": "Administrator access granted",
        "user_id": current_user["sub"],
    }
