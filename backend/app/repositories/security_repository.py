"""Persistence for tenant-scoped sessions and auditable security events."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.security_event import SecurityEvent
from app.models.user_session import UserSession


class SecurityRepository:
    """Centralize session/event queries while allowing nullable global events."""

    def __init__(self, db: Session, tenant_id: UUID | None) -> None:
        if tenant_id is not None:
            session_tenant_id = db.info.get("tenant_id")
            if session_tenant_id is not None and session_tenant_id != tenant_id:
                raise ValueError("The session is already bound to another tenant.")
        self.db = db
        self.tenant_id = tenant_id

    def _require_tenant(self) -> UUID:
        if self.tenant_id is None:
            raise ValueError("A tenant context is required for session/event reads.")
        return self.tenant_id

    def list_user_sessions(
        self,
        user_id: UUID,
        *,
        limit: int = 100,
    ) -> list[UserSession]:
        tenant_id = self._require_tenant()
        statement = (
            select(UserSession)
            .where(
                UserSession.user_id == user_id,
                UserSession.tenant_id == tenant_id,
            )
            .order_by(UserSession.created_at.desc())
            .limit(limit)
        )
        return list(self.db.scalars(statement).all())

    def get_user_session(
        self,
        session_id: UUID,
        user_id: UUID,
    ) -> UserSession | None:
        tenant_id = self._require_tenant()
        statement = select(UserSession).where(
            UserSession.id == session_id,
            UserSession.user_id == user_id,
            UserSession.tenant_id == tenant_id,
        )
        return self.db.scalar(statement)

    def list_active_sessions(
        self,
        user_id: UUID,
        *,
        excluded_session_id: UUID | None = None,
    ) -> list[UserSession]:
        tenant_id = self._require_tenant()
        statement = select(UserSession).where(
            UserSession.user_id == user_id,
            UserSession.tenant_id == tenant_id,
            UserSession.revoked_at.is_(None),
        )
        if excluded_session_id is not None:
            statement = statement.where(UserSession.id != excluded_session_id)
        return list(self.db.scalars(statement).all())

    def list_events(
        self,
        *,
        event_type: str | None = None,
        user_id: UUID | None = None,
        limit: int = 100,
    ) -> list[SecurityEvent]:
        tenant_id = self._require_tenant()
        statement = select(SecurityEvent).where(SecurityEvent.tenant_id == tenant_id)
        if event_type:
            statement = statement.where(SecurityEvent.event_type == event_type)
        if user_id:
            statement = statement.where(SecurityEvent.user_id == user_id)
        statement = statement.order_by(SecurityEvent.timestamp.desc()).limit(limit)
        return list(self.db.scalars(statement).all())

    def create_event(self, event: SecurityEvent) -> SecurityEvent:
        if event.tenant_id != self.tenant_id:
            raise ValueError("Security event tenant does not match repository tenant.")
        self.db.add(event)
        self.db.flush()
        return event
