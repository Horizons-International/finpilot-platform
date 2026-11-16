"""Async persistence for tenant-scoped security sessions and events."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.security_event import SecurityEvent
from app.models.user_session import UserSession


class AsyncSecurityRepository:
    """Tenant-scoped queries for user sessions and security events."""

    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        if db.info.get("tenant_id") not in (None, tenant_id):
            raise ValueError("The session is already bound to another tenant.")
        self.db = db
        self.tenant_id = tenant_id

    async def list_user_sessions(
        self,
        user_id: UUID,
        *,
        limit: int = 100,
    ) -> list[UserSession]:
        statement = (
            select(UserSession)
            .where(
                UserSession.user_id == user_id,
                UserSession.tenant_id == self.tenant_id,
            )
            .order_by(UserSession.created_at.desc())
            .limit(limit)
        )
        result = await self.db.scalars(statement)
        return list(result.all())

    async def get_user_session(
        self,
        session_id: UUID,
        user_id: UUID,
    ) -> UserSession | None:
        statement = select(UserSession).where(
            UserSession.id == session_id,
            UserSession.user_id == user_id,
            UserSession.tenant_id == self.tenant_id,
        )
        return await self.db.scalar(statement)

    async def list_active_sessions(
        self,
        user_id: UUID,
        *,
        excluded_session_id: UUID | None = None,
    ) -> list[UserSession]:
        statement = select(UserSession).where(
            UserSession.user_id == user_id,
            UserSession.tenant_id == self.tenant_id,
            UserSession.revoked_at.is_(None),
        )
        if excluded_session_id is not None:
            statement = statement.where(UserSession.id != excluded_session_id)
        result = await self.db.scalars(statement)
        return list(result.all())

    async def list_events(
        self,
        *,
        event_type: str | None = None,
        user_id: UUID | None = None,
        limit: int = 100,
    ) -> list[SecurityEvent]:
        statement = select(SecurityEvent).where(
            SecurityEvent.tenant_id == self.tenant_id
        )
        if event_type:
            statement = statement.where(SecurityEvent.event_type == event_type)
        if user_id:
            statement = statement.where(SecurityEvent.user_id == user_id)
        statement = statement.order_by(SecurityEvent.timestamp.desc()).limit(limit)
        result = await self.db.scalars(statement)
        return list(result.all())

    def add_event(self, event: SecurityEvent) -> SecurityEvent:
        if event.tenant_id != self.tenant_id:
            raise ValueError("Security event tenant does not match repository tenant.")
        self.db.add(event)
        return event
