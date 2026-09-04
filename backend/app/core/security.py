import re
from collections.abc import Callable
from datetime import timedelta
from typing import Any, cast

import bcrypt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.services.audit_service import AuditService
from app.utils.date_time import utc_now
from app.utils.enums import AuditEventType, UserRole
from app.utils.errors import unauthorized

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7


# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------


class Roles:
    ADMINISTRATOR = "Administrator"
    COMPLIANCE_OFFICER = "Compliance Officer"
    REVIEWER = "Reviewer"
    AUDITOR = "Auditor"


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
        expire = utc_now() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

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
        expire = utc_now() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

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

security = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict[str, Any]:
    """
    Validate the access token and return its payload.
    """

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

    if not payload.get("sub"):
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

    return payload


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
        current_user: dict[str, Any] = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> dict[str, Any]:
        user_role = current_user.get("role")

        if user_role not in allowed_roles:
            resource_id = None

            if resource_type is not None:
                resource_id = request.path_params.get(f"{resource_type}_id")

            audit_service = AuditService(db)

            audit_service.log_event(
                event_type=AuditEventType.ACCESS_DENIED,
                user_id=current_user.get("sub"),
                email=current_user.get("email"),
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

        return current_user

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
