"""Password, JWT, server-side session, and role-based access controls."""

import hashlib
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
from app.models.tenant import Tenant
from app.models.user import User
from app.models.user_session import UserSession
from app.services.audit_service import AuditService
from app.services.security_event_service import record_security_event
from app.utils.date_time import utc_now
from app.utils.enums import AuditEventType, TenantStatus, UserRole, UserStatus
from app.utils.errors import unauthorized

ALGORITHM = "HS256"
_PASSWORD_PREHASH_PREFIX = b"FinPilot password hash v2\x00"


def _password_material(password: str) -> bytes:
    """Normalize long input to fixed-size material before bcrypt.

    bcrypt only consumes the first 72 bytes. A domain-separated SHA-256 prehash
    prevents silent truncation. verify_password continues to accept legacy raw
    bcrypt hashes so deployments do not need to force a password reset.
    """
    digest = hashlib.sha256(_PASSWORD_PREHASH_PREFIX + password.encode("utf-8"))
    return digest.hexdigest().encode("ascii")


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------


def hash_password(password: str) -> str:
    password_bytes = password.encode("utf-8")
    if len(password_bytes) <= 72:
        # Keep the established hash format for ordinary passwords so an
        # overlapping deployment can still verify existing-style hashes.
        return bcrypt.hashpw(password_bytes, bcrypt.gensalt(rounds=12)).decode("utf-8")
    stored_hash = bcrypt.hashpw(_password_material(password), bcrypt.gensalt(rounds=12))
    return "v2$" + stored_hash.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify current hashes and legacy raw-bcrypt hashes without leaking errors."""
    try:
        if hashed_password.startswith("v2$"):
            return bcrypt.checkpw(
                _password_material(plain_password),
                hashed_password[3:].encode("utf-8"),
            )

        # Backward-compatible raw-bcrypt hashes are only valid for <=72 bytes.
        password_bytes = plain_password.encode("utf-8")
        if len(password_bytes) > 72:
            return False
        return bcrypt.checkpw(password_bytes, hashed_password.encode("utf-8"))
    except (ValueError, TypeError, UnicodeError):
        # Legacy bcrypt rejects input longer than its 72-byte limit.
        return False


# ---------------------------------------------------------------------------
# Access token
# ---------------------------------------------------------------------------


def create_access_token(
    data: dict[str, Any],
    expires_delta: timedelta | None = None,
) -> str:
    to_encode = data.copy()
    now = utc_now()
    configured_lifetime = timedelta(minutes=settings.JWT_ACCESS_EXPIRE_MINUTES)
    if expires_delta is not None and expires_delta > configured_lifetime:
        raise ValueError("Access token lifetime exceeds the configured maximum")
    lifetime = expires_delta if expires_delta is not None else configured_lifetime
    expire = now + lifetime
    to_encode.update({"iat": now, "exp": expire, "type": "access"})
    return str(jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM))


# ---------------------------------------------------------------------------
# Refresh token
# ---------------------------------------------------------------------------


def create_refresh_token(
    data: dict[str, Any],
    expires_delta: timedelta | None = None,
) -> str:
    to_encode = data.copy()
    now = utc_now()
    configured_lifetime = timedelta(days=settings.JWT_REFRESH_EXPIRE_DAYS)
    if expires_delta is not None and expires_delta > configured_lifetime:
        raise ValueError("Refresh token lifetime exceeds the configured maximum")
    lifetime = expires_delta if expires_delta is not None else configured_lifetime
    expire = now + lifetime
    to_encode.update({"iat": now, "exp": expire, "type": "refresh"})
    return str(jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM))


# ---------------------------------------------------------------------------
# Token decoding
# ---------------------------------------------------------------------------


def decode_access_token(token: str) -> dict[str, Any]:
    payload = jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[ALGORITHM],
        options={"require_exp": True},
    )
    if not isinstance(payload, dict):
        raise JWTError("Invalid token payload")
    if not isinstance(payload.get("sub"), str) or not payload["sub"].strip():
        raise JWTError("Missing or invalid subject claim")
    return cast(dict[str, Any], payload)


def decode_refresh_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[ALGORITHM],
            options={"require_exp": True},
        )
        if not isinstance(payload, dict):
            raise JWTError("Invalid token payload")
        if not isinstance(payload.get("sub"), str) or not payload["sub"].strip():
            raise JWTError("Missing or invalid subject claim")
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
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """Validate an unexpired access token and its live user/session/tenant."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_access_token(credentials.credentials)
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
    except (KeyError, TypeError, ValueError) as exc:
        raise unauthorized("Invalid access token") from exc

    if not payload.get("email"):
        raise unauthorized("Invalid access token")

    user = (
        db.query(User)
        .filter(User.id == user_id)
        .execution_options(
            skip_tenant_filter=True,
            tenant_scope_reason="authenticate by access-token subject",
        )
        .first()
    )
    if user is None:
        raise unauthorized("User not found")
    if user.status != UserStatus.ACTIVE or user.is_deleted:
        raise unauthorized("User account is not active")

    raw_session_id = payload.get("sid")
    request.state.session_id = None
    if raw_session_id is None:
        # Legacy unit-test tokens are tolerated outside production only.
        if settings.ENVIRONMENT == "production":
            raise unauthorized("Token is not associated with an active session")
    else:
        try:
            session_id = UUID(str(raw_session_id))
        except (TypeError, ValueError) as exc:
            raise unauthorized("Invalid authentication session") from exc
        user_session = (
            db.query(UserSession)
            .filter(UserSession.id == session_id)
            .execution_options(
                skip_tenant_filter=True,
                tenant_scope_reason=(
                    "validate session referenced by signed access token"
                ),
            )
            .first()
        )
        now = utc_now()
        if (
            user_session is None
            or user_session.user_id != user.id
            or user_session.tenant_id != user.tenant_id
            or user_session.revoked_at is not None
            or user_session.expires_at <= now
            or payload.get("tenant_id") != str(user.tenant_id)
        ):
            raise unauthorized("Session is invalid, expired, or revoked")

        idle_cutoff = now - timedelta(minutes=settings.SESSION_IDLE_TIMEOUT_MINUTES)
        if (
            user_session.last_seen_at is None
            or user_session.last_seen_at <= idle_cutoff
        ):
            user_session.revoked_at = now
            user_session.revoked_reason = "idle_timeout"
            record_security_event(
                db,
                event_type="SESSION_IDLE_TIMEOUT",
                user_id=user.id,
                tenant_id=user.tenant_id,
                email=user.email,
                ip_address=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
                request_path=request.url.path,
                details={"session_id": str(user_session.id)},
            )
            db.commit()
            raise unauthorized("Session expired after inactivity")

        request.state.session_id = str(user_session.id)

    tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
    if tenant is None:
        raise unauthorized("Tenant not found")
    if tenant.status != TenantStatus.ACTIVE:
        raise unauthorized("Tenant is not active")

    db.info["tenant_id"] = user.tenant_id
    db.info["tenant_user_id"] = user.id
    db.info["tenant_user_email"] = user.email
    db.info["tenant_ip_address"] = request.client.host if request.client else None
    db.info["tenant_user_agent"] = request.headers.get("user-agent")

    request.state.current_user_id = user.id
    request.state.current_user_email = user.email
    request.state.tenant_id = user.tenant_id

    # Bill authenticated API calls before dispatch, so exhausted plans fail closed.
    from app.services.subscription_service import (
        is_billing_exempt_path,
        record_subscription_usage,
    )

    if not is_billing_exempt_path(request.url.path):
        record_subscription_usage(db, user.tenant_id, "api_calls")

    return user


def require_platform_admin(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    if not current_user.is_platform_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform administrator access is required.",
        )
    return {
        "sub": str(current_user.id),
        "email": current_user.email,
        "role": current_user.role,
        "tenant_id": str(current_user.tenant_id),
        "is_platform_admin": True,
    }


def require_organization_admin(
    resource_type: str | None = None,
) -> Callable[..., Any]:
    return require_roles(
        UserRole.ADMINISTRATOR,
        UserRole.ORGANIZATION_ADMIN,
        resource_type=resource_type,
    )


# ---------------------------------------------------------------------------
# RBAC
# ---------------------------------------------------------------------------


def require_roles(
    *allowed_roles: UserRole,
    resource_type: str | None = None,
) -> Callable[..., Any]:
    """Create a reusable dependency that restricts an endpoint to these roles."""

    def role_checker(
        request: Request,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> dict[str, Any]:
        if current_user.role not in allowed_roles:
            resource_id = None
            if resource_type is not None:
                resource_id = request.path_params.get(f"{resource_type}_id")
            AuditService(db).log_event(
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
            "tenant_id": str(current_user.tenant_id),
            "is_platform_admin": current_user.is_platform_admin,
        }

    return role_checker


# ---------------------------------------------------------------------------
# Change Password
# ---------------------------------------------------------------------------


def validate_password(password: str) -> None:
    if len(password) < settings.PASSWORD_MIN_LENGTH:
        raise ValueError(
            f"Password must be at least {settings.PASSWORD_MIN_LENGTH} characters long"
        )
    if len(password) > 128:
        raise ValueError("Password must be no more than 128 characters long")
    if not re.search(r"[A-Z]", password):
        raise ValueError("Password must contain at least one uppercase letter")
    if not re.search(r"[a-z]", password):
        raise ValueError("Password must contain at least one lowercase letter")
    if not re.search(r"\d", password):
        raise ValueError("Password must contain at least one number")
    if not re.search(r"[^A-Za-z0-9]", password):
        raise ValueError("Password must contain at least one special character")
