"""Async authentication workflows backed by AsyncSession."""

from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from jwt.exceptions import InvalidTokenError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.mfa import decrypt_totp_secret, verify_totp
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_password,
    validate_password,
    verify_password,
)
from app.models.security_event import SecurityEvent
from app.models.tenant import Tenant
from app.models.user import User
from app.models.user_session import UserSession
from app.schemas.auth import (
    AuthUserResponse,
    ChangePasswordRequest,
    LoginResponse,
    RefreshTokenResponse,
)
from app.services.async_audit_service import AsyncAuditService
from app.utils.date_time import utc_now
from app.utils.enums import AuditEventType, TenantStatus, UserStatus
from app.utils.errors import bad_request, forbidden, not_found, unauthorized


class AsyncAuthService:
    """Login, refresh and password-change operations using async database I/O."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.audit_service = AsyncAuditService(db)

    async def _failure_count(self, email: str, ip_address: str | None) -> int:
        since = utc_now() - timedelta(minutes=settings.LOGIN_FAILURE_WINDOW_MINUTES)
        statement = select(func.count(SecurityEvent.id)).where(
            SecurityEvent.event_type == "LOGIN_FAILURE",
            SecurityEvent.email == email,
            SecurityEvent.timestamp >= since,
        )
        if ip_address is None:
            statement = statement.where(SecurityEvent.ip_address.is_(None))
        else:
            statement = statement.where(SecurityEvent.ip_address == ip_address)
        statement = statement.execution_options(
            skip_tenant_filter=True,
            tenant_scope_reason=(
                "throttle unauthenticated login attempts by email and IP"
            ),
        )
        return int(await self.db.scalar(statement) or 0)

    async def _record_blocked_login(
        self, email: str, ip_address: str | None, user_agent: str | None
    ) -> None:
        self.db.add(
            SecurityEvent(
                tenant_id=None,
                user_id=None,
                email=email[:255],
                event_type="LOGIN_BLOCKED",
                ip_address=ip_address[:45] if ip_address else None,
                user_agent=user_agent[:500] if user_agent else None,
                request_path="/api/v1/auth/login",
                details={"reason": "login_failure_threshold_exceeded"},
            )
        )
        await self.db.commit()

    async def _record_login_failure(
        self,
        *,
        user: User | None,
        email: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> None:
        if user is not None:
            self.db.info["tenant_id"] = user.tenant_id
        await self.audit_service.log_event(
            event_type=AuditEventType.LOGIN_FAILURE,
            user_id=user.id if user else None,
            email=user.email if user else email,
            resource_type="user",
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await self.db.commit()

    async def login(
        self,
        *,
        email: str,
        password: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
        mfa_code: str | None = None,
    ) -> LoginResponse:
        normalized_email = str(email).strip().lower()
        if (
            await self._failure_count(normalized_email, ip_address)
            >= settings.LOGIN_FAILURE_THRESHOLD
        ):
            await self._record_blocked_login(normalized_email, ip_address, user_agent)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many failed login attempts. Try again later.",
                headers={
                    "Retry-After": str(settings.LOGIN_FAILURE_WINDOW_MINUTES * 60)
                },
            )

        user = await self.db.scalar(
            select(User)
            .where(User.email == normalized_email, User.is_deleted.is_(False))
            .execution_options(
                skip_tenant_filter=True,
                tenant_scope_reason="login by globally unique user email",
            )
        )
        if user is None:
            await self._record_login_failure(
                user=None,
                email=normalized_email,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            raise unauthorized("Invalid email or password")

        self.db.info["tenant_id"] = user.tenant_id
        if not await run_in_threadpool(verify_password, password, user.password_hash):
            await self._record_login_failure(
                user=user,
                email=normalized_email,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            raise unauthorized("Invalid email or password")

        if user.status != UserStatus.ACTIVE or user.is_deleted:
            await self._record_login_failure(
                user=user,
                email=normalized_email,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            if user.status == UserStatus.LOCKED:
                raise forbidden("User account is locked")
            raise forbidden("User account is not active")

        if user.mfa_enabled:
            valid_code = False
            if mfa_code and user.mfa_secret_encrypted:
                try:
                    valid_code = verify_totp(
                        decrypt_totp_secret(user.mfa_secret_encrypted), mfa_code
                    )
                except ValueError:
                    valid_code = False
            if not valid_code:
                await self._record_login_failure(
                    user=user,
                    email=normalized_email,
                    ip_address=ip_address,
                    user_agent=user_agent,
                )
                self.db.add(
                    SecurityEvent(
                        tenant_id=user.tenant_id,
                        user_id=user.id,
                        email=user.email,
                        event_type="MFA_LOGIN_FAILURE",
                        ip_address=ip_address[:45] if ip_address else None,
                        user_agent=user_agent[:500] if user_agent else None,
                        request_path="/api/v1/auth/login",
                        details={"reason": "missing_or_invalid_code"},
                    )
                )
                await self.db.commit()
                raise unauthorized("Invalid email, password, or authentication code")

        tenant = await self.db.scalar(select(Tenant).where(Tenant.id == user.tenant_id))
        if tenant is None or tenant.status != TenantStatus.ACTIVE:
            await self._record_login_failure(
                user=user,
                email=normalized_email,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            raise unauthorized("Tenant is not active")

        now = utc_now()
        session_id = uuid4()
        self.db.add(
            UserSession(
                id=session_id,
                tenant_id=user.tenant_id,
                user_id=user.id,
                ip_address=ip_address,
                user_agent=user_agent,
                last_seen_at=now,
                expires_at=now + timedelta(days=settings.JWT_REFRESH_EXPIRE_DAYS),
            )
        )
        token_data: dict[str, Any] = {
            "sub": str(user.id),
            "email": user.email,
            "role": user.role,
            "tenant_id": str(user.tenant_id),
            "sid": str(session_id),
        }
        access_token = create_access_token(data=token_data)
        refresh_token = create_refresh_token(
            data=token_data,
            expires_delta=timedelta(days=settings.JWT_REFRESH_EXPIRE_DAYS),
        )
        await self.audit_service.log_event(
            event_type=AuditEventType.LOGIN_SUCCESS,
            user_id=user.id,
            email=user.email,
            resource_type="user",
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await self.db.commit()

        return LoginResponse(
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
                tenant_id=str(tenant.id),
                tenant_code=tenant.code,
            ),
        )

    async def refresh_token(self, refresh_token: str) -> RefreshTokenResponse:
        try:
            payload = decode_refresh_token(refresh_token)
        except InvalidTokenError as exc:
            raise unauthorized("Invalid or expired refresh token") from exc
        try:
            user_id = UUID(str(payload.get("sub")))
            session_id = UUID(str(payload.get("sid")))
        except (TypeError, ValueError):
            raise unauthorized("Invalid refresh token session")

        session = await self.db.scalar(
            select(UserSession)
            .where(UserSession.id == session_id)
            .execution_options(
                skip_tenant_filter=True,
                tenant_scope_reason=(
                    "validate session referenced by signed refresh token"
                ),
            )
        )
        now = utc_now()
        if (
            session is None
            or session.user_id != user_id
            or session.revoked_at is not None
            or session.expires_at <= now
        ):
            raise unauthorized("Session is invalid, expired, or revoked")

        user = await self.db.scalar(
            select(User)
            .where(User.id == user_id, User.is_deleted.is_(False))
            .execution_options(
                skip_tenant_filter=True,
                tenant_scope_reason="resolve user from signed refresh token",
            )
        )
        if user is None or user.status != UserStatus.ACTIVE:
            raise unauthorized("User account is not active")
        if user.tenant_id != session.tenant_id or payload.get("tenant_id") != str(
            user.tenant_id
        ):
            raise unauthorized("Invalid refresh token session")

        idle_cutoff = now - timedelta(minutes=settings.SESSION_IDLE_TIMEOUT_MINUTES)
        if session.last_seen_at is None or session.last_seen_at <= idle_cutoff:
            session.revoked_at = now
            session.revoked_reason = "idle_timeout"
            self.db.add(
                SecurityEvent(
                    tenant_id=user.tenant_id,
                    user_id=user.id,
                    email=user.email,
                    event_type="SESSION_IDLE_TIMEOUT",
                    request_path="/api/v1/auth/refresh",
                    details={"session_id": str(session.id), "flow": "refresh"},
                )
            )
            await self.db.commit()
            raise unauthorized("Session expired after inactivity")

        self.db.info["tenant_id"] = user.tenant_id
        access_token = create_access_token(
            data={
                "sub": str(user.id),
                "email": user.email,
                "role": user.role,
                "tenant_id": str(user.tenant_id),
                "sid": str(session.id),
            }
        )
        return RefreshTokenResponse(access_token=access_token, token_type="bearer")

    async def change_password(
        self,
        *,
        user_id: UUID,
        password_data: ChangePasswordRequest,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        user = await self.db.scalar(
            select(User).where(User.id == user_id, User.is_deleted.is_(False))
        )
        if user is None:
            raise not_found("User")
        self.db.info["tenant_id"] = user.tenant_id
        if not await run_in_threadpool(
            verify_password, password_data.current_password, user.password_hash
        ):
            raise bad_request("Current password is incorrect")
        if password_data.current_password == password_data.new_password:
            raise bad_request("New password must be different from current password")
        try:
            validate_password(password_data.new_password)
        except ValueError as exc:
            raise bad_request(str(exc)) from exc

        user.password_hash = await run_in_threadpool(
            hash_password, password_data.new_password
        )
        now = utc_now()
        sessions = list(
            (
                await self.db.scalars(
                    select(UserSession).where(
                        UserSession.user_id == user.id,
                        UserSession.tenant_id == user.tenant_id,
                        UserSession.revoked_at.is_(None),
                    )
                )
            ).all()
        )
        for user_session in sessions:
            user_session.revoked_at = now
            user_session.revoked_reason = "password_changed"

        await self.audit_service.log_event(
            event_type=AuditEventType.PASSWORD_CHANGE,
            user_id=user.id,
            email=user.email,
            resource_type="user",
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await self.db.commit()
