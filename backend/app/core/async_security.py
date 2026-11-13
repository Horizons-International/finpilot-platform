"""Async authentication and role-based access dependencies.

The synchronous security module remains available for routes that have not yet
been migrated. Async routes should use these dependencies so authentication,
session validation, tenant context and authorization use the request's
AsyncSession rather than opening a second synchronous database session.
"""

from collections.abc import Callable
from datetime import timedelta
from typing import Any
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import InvalidTokenError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_async_db
from app.core.security import decode_access_token
from app.models.security_event import SecurityEvent
from app.models.tenant import Tenant
from app.models.user import User
from app.models.user_session import UserSession
from app.services.async_audit_service import AsyncAuditService
from app.services.async_subscription_service import (
    is_billing_exempt_path,
    record_subscription_usage,
)
from app.utils.date_time import utc_now
from app.utils.enums import TenantStatus, UserRole, UserStatus
from app.utils.errors import unauthorized

_async_bearer = HTTPBearer(auto_error=False)


def _user_claims(user: User) -> dict[str, Any]:
    return {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role,
        "tenant_id": str(user.tenant_id),
        "is_platform_admin": user.is_platform_admin,
    }


async def _record_security_event(
    db: AsyncSession,
    *,
    event_type: str,
    user: User | None,
    request: Request,
    details: dict[str, Any] | None = None,
) -> None:
    db.add(
        SecurityEvent(
            tenant_id=user.tenant_id if user is not None else None,
            user_id=user.id if user is not None else None,
            email=user.email if user is not None else None,
            event_type=event_type[:64],
            ip_address=(request.client.host if request.client else None),
            user_agent=request.headers.get("user-agent"),
            request_path=request.url.path,
            details=details or {},
        )
    )
    await db.flush()


async def get_async_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_async_bearer),
    db: AsyncSession = Depends(get_async_db),
) -> User:
    """Validate access token, active user, server session and tenant status."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_access_token(credentials.credentials)
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    if payload.get("type") != "access":
        raise unauthorized("Invalid access token")

    try:
        user_id = UUID(str(payload["sub"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise unauthorized("Invalid access token") from exc

    if not payload.get("email"):
        raise unauthorized("Invalid access token")

    user = await db.scalar(
        select(User)
        .where(User.id == user_id)
        .execution_options(
            skip_tenant_filter=True,
            tenant_scope_reason="authenticate by signed access-token subject",
        )
    )
    if user is None:
        raise unauthorized("User not found")
    if user.status != UserStatus.ACTIVE or user.is_deleted:
        raise unauthorized("User account is not active")

    request.state.session_id = None
    raw_session_id = payload.get("sid")
    if raw_session_id is None:
        # Match the established compatibility policy for legacy test tokens.
        if settings.ENVIRONMENT == "production":
            raise unauthorized("Token is not associated with an active session")
    else:
        try:
            session_id = UUID(str(raw_session_id))
        except (TypeError, ValueError) as exc:
            raise unauthorized("Invalid authentication session") from exc

        user_session = await db.scalar(
            select(UserSession)
            .where(UserSession.id == session_id)
            .execution_options(
                skip_tenant_filter=True,
                tenant_scope_reason="validate session referenced by access token",
            )
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
            await _record_security_event(
                db,
                event_type="SESSION_IDLE_TIMEOUT",
                user=user,
                request=request,
                details={"session_id": str(user_session.id)},
            )
            await db.commit()
            raise unauthorized("Session expired after inactivity")

        request.state.session_id = str(user_session.id)

    tenant = await db.scalar(select(Tenant).where(Tenant.id == user.tenant_id))
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

    # Meter with native async SQL rather than bridging to the synchronous ORM.
    if not is_billing_exempt_path(request.url.path):
        await record_subscription_usage(db, user.tenant_id, "api_calls")

    return user


def require_async_roles(
    *allowed_roles: UserRole,
    resource_type: str | None = None,
) -> Callable[..., Any]:
    """Create an async role dependency for AsyncSession-backed endpoints."""

    async def role_checker(
        request: Request,
        current_user: User = Depends(get_async_current_user),
        db: AsyncSession = Depends(get_async_db),
    ) -> dict[str, Any]:
        if current_user.role not in allowed_roles:
            resource_id: UUID | None = None
            if resource_type is not None:
                raw_resource_id = request.path_params.get(f"{resource_type}_id")
                if raw_resource_id is None:
                    # Existing routes use domain-specific parameter names such
                    # as ``case_id`` and ``verification_case_id``. Preserve
                    # those IDs in access-denied audit events as well.
                    candidates = (
                        "case_id",
                        "verification_case_id",
                        "customer_id",
                        "rule_id",
                        "file_id",
                        "document_id",
                        "ticket_id",
                    )
                    raw_resource_id = next(
                        (
                            request.path_params.get(key)
                            for key in candidates
                            if request.path_params.get(key) is not None
                        ),
                        None,
                    )
                try:
                    resource_id = (
                        UUID(str(raw_resource_id)) if raw_resource_id else None
                    )
                except (TypeError, ValueError):
                    resource_id = None
            await AsyncAuditService(db).log_access_denied(
                resource_type=resource_type or "unknown",
                resource_id=resource_id,
                user_id=current_user.id,
                email=current_user.email,
                ip_address=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this resource.",
            )
        return _user_claims(current_user)

    return role_checker


async def require_async_platform_admin(
    current_user: User = Depends(get_async_current_user),
) -> dict[str, Any]:
    """Require an authenticated platform administrator using AsyncSession."""
    if not current_user.is_platform_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform administrator access is required.",
        )
    return _user_claims(current_user)
