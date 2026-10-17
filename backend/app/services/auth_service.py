"""Authentication workflows with bounded token and server-side session lifetimes."""

from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from jose import JWTError
from sqlalchemy import func
from sqlalchemy.orm import Session

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
from app.repositories.user_repository import UserRepository
from app.schemas.auth import (
    AuthUserResponse,
    ChangePasswordRequest,
    LoginResponse,
    RefreshTokenResponse,
)
from app.services.audit_service import AuditService
from app.services.security_event_service import record_security_event
from app.utils.date_time import utc_now
from app.utils.enums import AuditEventType, TenantStatus, UserStatus
from app.utils.errors import bad_request, forbidden, not_found, unauthorized


class AuthService:
    def __init__(self, db: Session):
        self.db = db
        self.user_repository = UserRepository(db)
        self.audit_service = AuditService(db)

    def _failure_count(self, email: str, ip_address: str | None) -> int:
        since = utc_now() - timedelta(minutes=settings.LOGIN_FAILURE_WINDOW_MINUTES)
        query = self.db.query(func.count(SecurityEvent.id)).filter(
            SecurityEvent.event_type == "LOGIN_FAILURE",
            SecurityEvent.email == email,
            SecurityEvent.timestamp >= since,
        )
        if ip_address is None:
            query = query.filter(SecurityEvent.ip_address.is_(None))
        else:
            query = query.filter(SecurityEvent.ip_address == ip_address)
        return int(
            query.execution_options(
                skip_tenant_filter=True,
                tenant_scope_reason=(
                    "throttle unauthenticated login attempts by email and IP"
                ),
            ).scalar()
            or 0
        )

    def _record_blocked_login(
        self, email: str, ip_address: str | None, user_agent: str | None
    ) -> None:
        record_security_event(
            self.db,
            event_type="LOGIN_BLOCKED",
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            details={"reason": "login_failure_threshold_exceeded"},
            commit=True,
        )

    def login(
        self,
        email: str,
        password: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
        mfa_code: str | None = None,
    ) -> LoginResponse:
        normalized_email = str(email).strip().lower()
        if (
            self._failure_count(normalized_email, ip_address)
            >= settings.LOGIN_FAILURE_THRESHOLD
        ):
            self._record_blocked_login(normalized_email, ip_address, user_agent)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many failed login attempts. Try again later.",
                headers={
                    "Retry-After": str(settings.LOGIN_FAILURE_WINDOW_MINUTES * 60)
                },
            )

        user = self.user_repository.get_by_email(normalized_email)
        if user is None:
            self.audit_service.log_event(
                event_type=AuditEventType.LOGIN_FAILURE,
                email=normalized_email,
                resource_type="user",
                ip_address=ip_address,
                user_agent=user_agent,
            )
            self.db.commit()
            raise unauthorized("Invalid email or password")

        # Bind known-user events to the tenant before storing audit/security data.
        self.db.info["tenant_id"] = user.tenant_id
        if not verify_password(password, user.password_hash):
            self.audit_service.log_event(
                event_type=AuditEventType.LOGIN_FAILURE,
                user_id=user.id,
                email=user.email,
                resource_type="user",
                ip_address=ip_address,
                user_agent=user_agent,
            )
            self.db.commit()
            raise unauthorized("Invalid email or password")

        if user.status != UserStatus.ACTIVE or user.is_deleted:
            self.audit_service.log_event(
                event_type=AuditEventType.LOGIN_FAILURE,
                user_id=user.id,
                email=user.email,
                resource_type="user",
                ip_address=ip_address,
                user_agent=user_agent,
            )
            self.db.commit()
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
                self.audit_service.log_event(
                    event_type=AuditEventType.LOGIN_FAILURE,
                    user_id=user.id,
                    email=user.email,
                    resource_type="user",
                    ip_address=ip_address,
                    user_agent=user_agent,
                )
                record_security_event(
                    self.db,
                    event_type="MFA_LOGIN_FAILURE",
                    user_id=user.id,
                    tenant_id=user.tenant_id,
                    email=user.email,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    details={"reason": "missing_or_invalid_code"},
                )
                self.db.commit()
                raise unauthorized("Invalid email, password, or authentication code")

        tenant = self.db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
        if tenant is None or tenant.status != TenantStatus.ACTIVE:
            self.audit_service.log_event(
                event_type=AuditEventType.LOGIN_FAILURE,
                user_id=user.id,
                email=user.email,
                resource_type="user",
                ip_address=ip_address,
                user_agent=user_agent,
            )
            self.db.commit()
            raise unauthorized("Tenant is not active")

        now = utc_now()
        session_id = uuid4()
        user_session = UserSession(
            id=session_id,
            tenant_id=user.tenant_id,
            user_id=user.id,
            ip_address=ip_address,
            user_agent=user_agent,
            last_seen_at=now,
            expires_at=now + timedelta(days=settings.JWT_REFRESH_EXPIRE_DAYS),
        )
        self.db.add(user_session)

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

        self.audit_service.log_event(
            event_type=AuditEventType.LOGIN_SUCCESS,
            user_id=user.id,
            email=user.email,
            resource_type="user",
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.db.commit()

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

    def refresh_token(self, refresh_token: str) -> RefreshTokenResponse:
        try:
            payload = decode_refresh_token(refresh_token)
        except JWTError as exc:
            raise unauthorized("Invalid or expired refresh token") from exc

        try:
            user_id = UUID(str(payload.get("sub")))
            session_id = UUID(str(payload.get("sid")))
        except (TypeError, ValueError):
            raise unauthorized("Invalid refresh token session")

        session = (
            self.db.query(UserSession)
            .filter(UserSession.id == session_id)
            .execution_options(
                skip_tenant_filter=True,
                tenant_scope_reason=(
                    "validate session referenced by signed refresh token"
                ),
            )
            .first()
        )
        now = utc_now()
        if (
            session is None
            or session.user_id != user_id
            or session.revoked_at is not None
            or session.expires_at <= now
        ):
            raise unauthorized("Session is invalid, expired, or revoked")

        user = (
            self.db.query(User)
            .filter(User.id == user_id, User.is_deleted.is_(False))
            .execution_options(
                skip_tenant_filter=True,
                tenant_scope_reason="resolve user from signed refresh token",
            )
            .first()
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
            record_security_event(
                self.db,
                event_type="SESSION_IDLE_TIMEOUT",
                user_id=user.id,
                tenant_id=user.tenant_id,
                email=user.email,
                request_path="/api/v1/auth/refresh",
                details={"session_id": str(session.id), "flow": "refresh"},
            )
            self.db.commit()
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

    def change_password(
        self,
        user_id: UUID,
        password_data: ChangePasswordRequest,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        user = self.user_repository.get_by_id(user_id)
        if user is None:
            raise not_found("User")
        if not verify_password(password_data.current_password, user.password_hash):
            raise bad_request("Current password is incorrect")
        if password_data.current_password == password_data.new_password:
            raise bad_request("New password must be different from current password")
        try:
            validate_password(password_data.new_password)
        except ValueError as exc:
            raise bad_request(str(exc)) from exc

        user.password_hash = hash_password(password_data.new_password)
        now = utc_now()
        sessions = list(
            self.db.query(UserSession)
            .filter(
                UserSession.user_id == user.id,
                UserSession.tenant_id == user.tenant_id,
                UserSession.revoked_at.is_(None),
            )
            .all()
        )
        for session in sessions:
            session.revoked_at = now
            session.revoked_reason = "password_changed"

        self.audit_service.log_event(
            event_type=AuditEventType.PASSWORD_CHANGE,
            user_id=user.id,
            email=user.email,
            resource_type="user",
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.db.commit()
