"""MFA, revocable sessions, and security-event query operations."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.mfa import (
    build_otpauth_uri,
    decrypt_totp_secret,
    encrypt_totp_secret,
    generate_totp_secret,
    verify_totp,
)
from app.core.security import verify_password
from app.models.security_event import SecurityEvent
from app.models.user import User
from app.models.user_session import UserSession
from app.schemas.security import (
    MFAEnrollResponse,
    SecurityEventResponse,
    SecuritySessionResponse,
)
from app.services.security_event_service import record_security_event
from app.utils.date_time import utc_now
from app.utils.errors import bad_request, conflict, forbidden, not_found


class SecurityService:
    def __init__(self, db: Session, user: User) -> None:
        self.db = db
        self.user = user
        self.tenant_id = user.tenant_id
        self.db.info["tenant_id"] = user.tenant_id

    def begin_mfa_enrollment(self, current_password: str) -> MFAEnrollResponse:
        if self.user.mfa_enabled:
            raise conflict("MFA is already enabled for this account.")
        if not verify_password(current_password, self.user.password_hash):
            raise forbidden("Current password is incorrect.")
        secret = generate_totp_secret()
        self.user.mfa_secret_encrypted = encrypt_totp_secret(secret)
        self.user.mfa_enrolled_at = None
        self.db.commit()
        self.db.refresh(self.user)
        return MFAEnrollResponse(
            secret=secret,
            otpauth_uri=build_otpauth_uri(secret, self.user.email),
            message=(
                "Scan the URI in your authenticator app, then confirm "
                "with a current code."
            ),
        )

    def confirm_mfa_enrollment(
        self, code: str, ip_address: str | None, user_agent: str | None
    ) -> None:
        if self.user.mfa_enabled:
            raise conflict("MFA is already enabled for this account.")
        if not self.user.mfa_secret_encrypted:
            raise bad_request("Start MFA enrollment before confirming it.")
        try:
            secret = decrypt_totp_secret(self.user.mfa_secret_encrypted)
        except ValueError as exc:
            raise bad_request(
                "The stored MFA enrollment is invalid. Start enrollment again."
            ) from exc
        if not verify_totp(secret, code):
            record_security_event(
                self.db,
                event_type="MFA_ENROLLMENT_FAILED",
                user_id=self.user.id,
                tenant_id=self.tenant_id,
                email=self.user.email,
                ip_address=ip_address,
                user_agent=user_agent,
                details={"reason": "invalid_totp"},
            )
            self.db.commit()
            raise bad_request("The authentication code is invalid.")
        self.user.mfa_enabled = True
        self.user.mfa_enrolled_at = utc_now()
        record_security_event(
            self.db,
            event_type="MFA_ENABLED",
            user_id=self.user.id,
            tenant_id=self.tenant_id,
            email=self.user.email,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.db.commit()
        self.db.refresh(self.user)

    def disable_mfa(
        self,
        *,
        current_password: str,
        code: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> None:
        if not self.user.mfa_enabled or not self.user.mfa_secret_encrypted:
            raise bad_request("MFA is not enabled for this account.")
        if not verify_password(current_password, self.user.password_hash):
            raise forbidden("Current password is incorrect.")
        try:
            secret = decrypt_totp_secret(self.user.mfa_secret_encrypted)
        except ValueError as exc:
            raise bad_request(
                "The stored MFA secret is invalid; contact an administrator."
            ) from exc
        if not verify_totp(secret, code):
            record_security_event(
                self.db,
                event_type="MFA_DISABLE_FAILED",
                user_id=self.user.id,
                tenant_id=self.tenant_id,
                email=self.user.email,
                ip_address=ip_address,
                user_agent=user_agent,
                details={"reason": "invalid_totp"},
            )
            self.db.commit()
            raise forbidden("Authentication code is invalid.")
        self.user.mfa_enabled = False
        self.user.mfa_secret_encrypted = None
        self.user.mfa_enrolled_at = None
        record_security_event(
            self.db,
            event_type="MFA_DISABLED",
            user_id=self.user.id,
            tenant_id=self.tenant_id,
            email=self.user.email,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self._revoke_active_sessions(reason="mfa_disabled")
        self.db.commit()
        self.db.refresh(self.user)

    def list_sessions(
        self, current_session_id: UUID | None
    ) -> list[SecuritySessionResponse]:
        sessions = list(
            self.db.scalars(
                select(UserSession)
                .where(
                    UserSession.user_id == self.user.id,
                    UserSession.tenant_id == self.tenant_id,
                )
                .order_by(UserSession.created_at.desc())
                .limit(100)
            ).all()
        )
        return [
            SecuritySessionResponse(
                id=item.id,
                ip_address=item.ip_address,
                user_agent=item.user_agent,
                created_at=item.created_at,
                last_seen_at=item.last_seen_at,
                expires_at=item.expires_at,
                revoked_at=item.revoked_at,
                revoked_reason=item.revoked_reason,
                is_current=item.id == current_session_id,
            )
            for item in sessions
        ]

    def revoke_session(
        self,
        session_id: UUID,
        *,
        ip_address: str | None,
        user_agent: str | None,
    ) -> None:
        session = self.db.scalar(
            select(UserSession).where(
                UserSession.id == session_id,
                UserSession.user_id == self.user.id,
                UserSession.tenant_id == self.tenant_id,
            )
        )
        if session is None:
            raise not_found("Session")
        if session.revoked_at is not None:
            return
        session.revoked_at = utc_now()
        session.revoked_reason = "user_revoked"
        record_security_event(
            self.db,
            event_type="SESSION_REVOKED",
            user_id=self.user.id,
            tenant_id=self.tenant_id,
            email=self.user.email,
            ip_address=ip_address,
            user_agent=user_agent,
            details={"session_id": str(session.id), "reason": "user_revoked"},
        )
        self.db.commit()

    def revoke_other_sessions(
        self,
        current_session_id: UUID | None,
        *,
        ip_address: str | None,
        user_agent: str | None,
    ) -> int:
        statement = select(UserSession).where(
            UserSession.user_id == self.user.id,
            UserSession.tenant_id == self.tenant_id,
            UserSession.revoked_at.is_(None),
        )
        if current_session_id is not None:
            statement = statement.where(UserSession.id != current_session_id)
        sessions = list(self.db.scalars(statement).all())
        now = utc_now()
        for session in sessions:
            session.revoked_at = now
            session.revoked_reason = "other_sessions_revoked"
        if sessions:
            record_security_event(
                self.db,
                event_type="SESSIONS_REVOKED",
                user_id=self.user.id,
                tenant_id=self.tenant_id,
                email=self.user.email,
                ip_address=ip_address,
                user_agent=user_agent,
                details={"count": len(sessions), "reason": "other_sessions_revoked"},
            )
            self.db.commit()
        return len(sessions)

    def list_events(
        self,
        *,
        event_type: str | None = None,
        user_id: UUID | None = None,
        limit: int = 100,
    ) -> list[SecurityEventResponse]:
        statement = select(SecurityEvent).where(
            SecurityEvent.tenant_id == self.tenant_id
        )
        if event_type:
            statement = statement.where(SecurityEvent.event_type == event_type)
        if user_id:
            statement = statement.where(SecurityEvent.user_id == user_id)
        events = list(
            self.db.scalars(
                statement.order_by(SecurityEvent.timestamp.desc()).limit(limit)
            ).all()
        )
        return [SecurityEventResponse.model_validate(event) for event in events]

    def _revoke_active_sessions(self, *, reason: str) -> int:
        sessions = list(
            self.db.scalars(
                select(UserSession).where(
                    UserSession.user_id == self.user.id,
                    UserSession.tenant_id == self.tenant_id,
                    UserSession.revoked_at.is_(None),
                )
            ).all()
        )
        now = utc_now()
        for session in sessions:
            session.revoked_at = now
            session.revoked_reason = reason
        return len(sessions)
