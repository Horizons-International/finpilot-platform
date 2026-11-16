"""Native async MFA, revocable sessions, and security-event operations."""

from typing import Any
from uuid import UUID

import anyio
from sqlalchemy.ext.asyncio import AsyncSession

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
from app.repositories.async_security_repository import AsyncSecurityRepository
from app.schemas.security import (
    MFAEnrollResponse,
    SecurityEventResponse,
    SecuritySessionResponse,
)
from app.utils.date_time import utc_now
from app.utils.errors import bad_request, conflict, forbidden, not_found


class AsyncSecurityService:
    """Async implementation of the enterprise security controls."""

    def __init__(self, db: AsyncSession, user: User) -> None:
        if user.tenant_id is None:
            raise ValueError("A tenant-bound user is required for security controls.")
        self.db = db
        self.user = user
        self.tenant_id = user.tenant_id
        self.db.info["tenant_id"] = user.tenant_id
        self.repository = AsyncSecurityRepository(db, tenant_id=user.tenant_id)

    async def _verify_current_password(self, password: str) -> bool:
        # bcrypt is CPU-bound and synchronous. Keep it off the event-loop thread.
        return await anyio.to_thread.run_sync(
            verify_password, password, self.user.password_hash
        )

    def _record_event(
        self,
        *,
        event_type: str,
        ip_address: str | None,
        user_agent: str | None,
        details: dict[str, Any] | None = None,
    ) -> None:
        event = SecurityEvent(
            tenant_id=self.tenant_id,
            user_id=self.user.id,
            email=self.user.email[:255] if self.user.email else None,
            event_type=event_type[:64],
            ip_address=ip_address[:45] if ip_address else None,
            user_agent=user_agent[:500] if user_agent else None,
            details=details or {},
        )
        self.repository.add_event(event)

    async def begin_mfa_enrollment(self, current_password: str) -> MFAEnrollResponse:
        if self.user.mfa_enabled:
            raise conflict("MFA is already enabled for this account.")
        if not await self._verify_current_password(current_password):
            raise forbidden("Current password is incorrect.")

        secret = generate_totp_secret()
        self.user.mfa_secret_encrypted = encrypt_totp_secret(secret)
        self.user.mfa_enrolled_at = None
        await self.db.commit()
        await self.db.refresh(self.user)
        return MFAEnrollResponse(
            secret=secret,
            otpauth_uri=build_otpauth_uri(secret, self.user.email),
            message=(
                "Scan the URI in your authenticator app, then confirm "
                "with a current code."
            ),
        )

    async def confirm_mfa_enrollment(
        self,
        code: str,
        ip_address: str | None,
        user_agent: str | None,
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
            self._record_event(
                event_type="MFA_ENROLLMENT_FAILED",
                ip_address=ip_address,
                user_agent=user_agent,
                details={"reason": "invalid_totp"},
            )
            await self.db.commit()
            raise bad_request("The authentication code is invalid.")

        self.user.mfa_enabled = True
        self.user.mfa_enrolled_at = utc_now()
        self._record_event(
            event_type="MFA_ENABLED",
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await self.db.commit()
        await self.db.refresh(self.user)

    async def disable_mfa(
        self,
        *,
        current_password: str,
        code: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> None:
        if not self.user.mfa_enabled or not self.user.mfa_secret_encrypted:
            raise bad_request("MFA is not enabled for this account.")
        if not await self._verify_current_password(current_password):
            raise forbidden("Current password is incorrect.")

        try:
            secret = decrypt_totp_secret(self.user.mfa_secret_encrypted)
        except ValueError as exc:
            raise bad_request(
                "The stored MFA secret is invalid; contact an administrator."
            ) from exc

        if not verify_totp(secret, code):
            self._record_event(
                event_type="MFA_DISABLE_FAILED",
                ip_address=ip_address,
                user_agent=user_agent,
                details={"reason": "invalid_totp"},
            )
            await self.db.commit()
            raise forbidden("Authentication code is invalid.")

        self.user.mfa_enabled = False
        self.user.mfa_secret_encrypted = None
        self.user.mfa_enrolled_at = None
        self._record_event(
            event_type="MFA_DISABLED",
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await self._revoke_active_sessions(reason="mfa_disabled")
        await self.db.commit()
        await self.db.refresh(self.user)

    async def list_sessions(
        self, current_session_id: UUID | None
    ) -> list[SecuritySessionResponse]:
        sessions = await self.repository.list_user_sessions(self.user.id, limit=100)
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

    async def revoke_session(
        self,
        session_id: UUID,
        *,
        ip_address: str | None,
        user_agent: str | None,
    ) -> None:
        session = await self.repository.get_user_session(session_id, self.user.id)
        if session is None:
            raise not_found("Session")
        if session.revoked_at is not None:
            return

        session.revoked_at = utc_now()
        session.revoked_reason = "user_revoked"
        self._record_event(
            event_type="SESSION_REVOKED",
            ip_address=ip_address,
            user_agent=user_agent,
            details={"session_id": str(session.id), "reason": "user_revoked"},
        )
        await self.db.commit()

    async def revoke_other_sessions(
        self,
        current_session_id: UUID | None,
        *,
        ip_address: str | None,
        user_agent: str | None,
    ) -> int:
        sessions = await self.repository.list_active_sessions(
            self.user.id,
            excluded_session_id=current_session_id,
        )
        now = utc_now()
        for session in sessions:
            session.revoked_at = now
            session.revoked_reason = "other_sessions_revoked"

        if sessions:
            self._record_event(
                event_type="SESSIONS_REVOKED",
                ip_address=ip_address,
                user_agent=user_agent,
                details={
                    "count": len(sessions),
                    "reason": "other_sessions_revoked",
                },
            )
            await self.db.commit()
        return len(sessions)

    async def list_events(
        self,
        *,
        event_type: str | None = None,
        user_id: UUID | None = None,
        limit: int = 100,
    ) -> list[SecurityEventResponse]:
        events = await self.repository.list_events(
            event_type=event_type,
            user_id=user_id,
            limit=limit,
        )
        return [SecurityEventResponse.model_validate(event) for event in events]

    async def _revoke_active_sessions(self, *, reason: str) -> int:
        sessions = await self.repository.list_active_sessions(self.user.id)
        now = utc_now()
        for session in sessions:
            session.revoked_at = now
            session.revoked_reason = reason
        return len(sessions)
