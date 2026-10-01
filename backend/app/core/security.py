import re
from collections.abc import Callable
from datetime import timedelta
from typing import Any, cast
from uuid import UUID

import bcrypt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.user import User
from app.services.audit_service import AuditService
from app.utils.date_time import utc_now
from app.utils.enums import AuditEventType, UserRole, UserStatus
from app.utils.errors import unauthorized

ALGORITHM = "HS256"


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------


def hash_password(password: str) -> str:
    password_bytes = password.encode("utf-8")

    salt = bcrypt.gensalt()

    hashed = bcrypt.hashpw(password_bytes, salt)

    return hashed.decode("utf-8")


def verify_password(
    plain_password: str,
    hashed_password: str,
) -> bool:
    password_bytes = plain_password.encode("utf-8")
    hashed_bytes = hashed_password.encode("utf-8")

    return bcrypt.checkpw(
        password_bytes,
        hashed_bytes,
    )


# ---------------------------------------------------------------------------
# Access token
# ---------------------------------------------------------------------------


def create_access_token(
    data: dict,
    expires_delta: timedelta | None = None,
) -> str:
    to_encode = data.copy()

    if expires_delta:
        expire = utc_now() + expires_delta
    else:
        expire = utc_now() + timedelta(minutes=settings.JWT_ACCESS_EXPIRE_MINUTES)

    to_encode.update(
        {
            "exp": expire,
            "type": "access",
        }
    )

    return str(
        jwt.encode(
            to_encode,
            settings.SECRET_KEY,
            algorithm=ALGORITHM,
        )
    )


# ---------------------------------------------------------------------------
# Refresh token
# ---------------------------------------------------------------------------


def create_refresh_token(
    data: dict,
    expires_delta: timedelta | None = None,
) -> str:
    to_encode = data.copy()

    if expires_delta:
        expire = utc_now() + expires_delta
    else:
        expire = utc_now() + timedelta(days=settings.JWT_REFRESH_EXPIRE_DAYS)

    to_encode.update(
        {
            "exp": expire,
            "type": "refresh",
        }
    )

    return str(
        jwt.encode(
            to_encode,
            settings.SECRET_KEY,
            algorithm=ALGORITHM,
        )
    )


# ---------------------------------------------------------------------------
# Token decoding
# ---------------------------------------------------------------------------


def decode_access_token(token: str) -> dict[str, Any]:
    payload = jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[ALGORITHM],
    )

    return cast(dict[str, Any], payload)


def decode_refresh_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[ALGORITHM],
        )

        if payload.get("type") != "refresh":
            raise unauthorized("Invalid refresh token")

        return cast(dict[str, Any], payload)
    except JWTError as exc:
        raise unauthorized("Invalid or expired refresh token") from exc


# ---------------------------------------------------------------------------
# Authentication dependency
# ---------------------------------------------------------------------------

security = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """
    Validate the access token and return its payload.
    """

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    try:
        payload = decode_access_token(token)
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_id = UUID(str(payload["sub"]))
    except (KeyError, TypeError, ValueError):
        raise unauthorized("Invalid access token")

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not payload.get("email"):
        raise HTTPException(
            status_code=401,
            detail="Invalid access token.",
        )

    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise unauthorized("User not found")

    if user.status != UserStatus.ACTIVE:
        raise unauthorized("User account is not active")

    return user


# ---------------------------------------------------------------------------
# RBAC
# ---------------------------------------------------------------------------


def require_roles(
    *allowed_roles: UserRole,
    resource_type: str | None = None,
) -> Callable[..., Any]:
    """
    Create a reusable dependency that restricts an endpoint
    to the specified roles.
    """

    def role_checker(
        request: Request,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> dict[str, Any]:
        if current_user.role not in allowed_roles:
            resource_id = None

            if resource_type is not None:
                resource_id = request.path_params.get(f"{resource_type}_id")

            audit_service = AuditService(db)

            audit_service.log_event(
                event_type=AuditEventType.ACCESS_DENIED,
                user_id=current_user.id,
                email=current_user.email,
                ip_address=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
                resource_type=resource_type,
                resource_id=resource_id,
            )

            db.commit()

            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this resource.",
            )

        return {
            "sub": str(current_user.id),
            "email": current_user.email,
            "role": current_user.role,
        }

    return role_checker


# ---------------------------------------------------------------------------
# Change Password
# ---------------------------------------------------------------------------


def validate_password(password: str) -> None:
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters long")

    if not re.search(r"[A-Z]", password):
        raise ValueError("Password must contain at least one uppercase letter")

    if not re.search(r"[a-z]", password):
        raise ValueError("Password must contain at least one lowercase letter")

    if not re.search(r"\d", password):
        raise ValueError("Password must contain at least one number")

    if not re.search(r"[^A-Za-z0-9]", password):
        raise ValueError("Password must contain at least one special character")
