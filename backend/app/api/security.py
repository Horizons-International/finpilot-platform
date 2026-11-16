"""Enterprise security controls: MFA, session management, and security events."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.async_security import get_async_current_user, require_async_roles
from app.core.database import get_async_db
from app.core.responses import APIResponse
from app.models.user import User
from app.schemas.security import (
    MFACodeRequest,
    MFADisableRequest,
    MFAEnrollRequest,
    MFAEnrollResponse,
    SecurityEventResponse,
    SecuritySessionResponse,
)
from app.services.async_security_service import AsyncSecurityService
from app.utils.enums import UserRole

router = APIRouter(prefix="/api/v1/security", tags=["Enterprise Security"])
_ADMIN_ROLES = (UserRole.ADMINISTRATOR, UserRole.ORGANIZATION_ADMIN)


def _metadata(request: Request) -> tuple[str | None, str | None]:
    return (
        request.client.host if request.client else None,
        request.headers.get("user-agent"),
    )


def _service(db: AsyncSession, user: User) -> AsyncSecurityService:
    return AsyncSecurityService(db, user)


def _current_session_id(request: Request) -> UUID | None:
    raw_session_id = getattr(request.state, "session_id", None)
    try:
        return UUID(str(raw_session_id)) if raw_session_id else None
    except (TypeError, ValueError):
        return None


@router.post(
    "/mfa/enroll",
    response_model=APIResponse[MFAEnrollResponse],
    summary="Begin MFA enrollment",
)
async def begin_mfa_enrollment(
    payload: MFAEnrollRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_async_current_user),
) -> APIResponse[MFAEnrollResponse]:
    enrollment = await _service(db, current_user).begin_mfa_enrollment(
        payload.current_password
    )
    return APIResponse(
        success=True,
        message=(
            "MFA enrollment started. Store the secret securely and confirm the code."
        ),
        data=enrollment,
    )


@router.post(
    "/mfa/confirm",
    response_model=APIResponse[dict[str, bool]],
    summary="Confirm and enable MFA",
)
async def confirm_mfa_enrollment(
    payload: MFACodeRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_async_current_user),
) -> APIResponse[dict[str, bool]]:
    ip_address, user_agent = _metadata(request)
    await _service(db, current_user).confirm_mfa_enrollment(
        payload.code, ip_address, user_agent
    )
    return APIResponse(
        success=True,
        message="MFA enabled successfully.",
        data={"mfa_enabled": True},
    )


@router.post(
    "/mfa/disable",
    response_model=APIResponse[dict[str, bool]],
    summary="Disable MFA",
)
async def disable_mfa(
    payload: MFADisableRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_async_current_user),
) -> APIResponse[dict[str, bool]]:
    ip_address, user_agent = _metadata(request)
    await _service(db, current_user).disable_mfa(
        current_password=payload.current_password,
        code=payload.code,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return APIResponse(
        success=True, message="MFA disabled.", data={"mfa_enabled": False}
    )


@router.get(
    "/sessions",
    response_model=APIResponse[list[SecuritySessionResponse]],
    summary="List your sessions",
)
async def list_sessions(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_async_current_user),
) -> APIResponse[list[SecuritySessionResponse]]:
    sessions = await _service(db, current_user).list_sessions(
        _current_session_id(request)
    )
    return APIResponse(
        success=True, message="Sessions retrieved successfully.", data=sessions
    )


@router.post(
    "/sessions/revoke-others",
    response_model=APIResponse[dict[str, int]],
    summary="Revoke other active sessions",
)
async def revoke_other_sessions(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_async_current_user),
) -> APIResponse[dict[str, int]]:
    ip_address, user_agent = _metadata(request)
    count = await _service(db, current_user).revoke_other_sessions(
        _current_session_id(request),
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return APIResponse(
        success=True,
        message="Other sessions revoked.",
        data={"revoked_count": count},
    )


@router.post(
    "/sessions/{session_id}/revoke",
    response_model=APIResponse[dict[str, str]],
    summary="Revoke one of your sessions",
)
async def revoke_session(
    session_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_async_current_user),
) -> APIResponse[dict[str, str]]:
    ip_address, user_agent = _metadata(request)
    await _service(db, current_user).revoke_session(
        session_id,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return APIResponse(
        success=True,
        message="Session revoked.",
        data={"session_id": str(session_id)},
    )


@router.get(
    "/events",
    response_model=APIResponse[list[SecurityEventResponse]],
    summary="List tenant security events",
)
async def list_security_events(
    event_type: str | None = Query(default=None, max_length=64),
    user_id: UUID | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    db: AsyncSession = Depends(get_async_db),
    _: dict[str, Any] = Depends(
        require_async_roles(*_ADMIN_ROLES, resource_type="security_event")
    ),
    current_user: User = Depends(get_async_current_user),
) -> APIResponse[list[SecurityEventResponse]]:
    events = await _service(db, current_user).list_events(
        event_type=event_type,
        user_id=user_id,
        limit=limit,
    )
    return APIResponse(
        success=True,
        message="Security events retrieved successfully.",
        data=events,
    )
