"""Tenant-scoped filters for audit evidence."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.audit_event import AuditEvent


class AuditEventRepository:
    def __init__(self, db: Session, tenant_id: UUID | None) -> None:
        self.db = db
        self.tenant_id = tenant_id

    def search(
        self,
        *,
        action: str | None = None,
        entity_type: str | None = None,
        entity_id: UUID | None = None,
        user_id: UUID | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[AuditEvent], int]:
        if self.tenant_id is None:
            raise ValueError("A tenant context is required to search audit events")
        if page < 1:
            raise ValueError("page must be at least 1")
        if not 1 <= page_size <= 200:
            raise ValueError("page_size must be between 1 and 200")
        if start_at is not None and end_at is not None and start_at > end_at:
            raise ValueError("start_at cannot be later than end_at")

        conditions = [AuditEvent.tenant_id == self.tenant_id]
        if action:
            conditions.append(AuditEvent.action == action.strip().upper())
        if entity_type:
            conditions.append(AuditEvent.entity_type == entity_type.strip())
        if entity_id is not None:
            conditions.append(AuditEvent.entity_id == entity_id)
        if user_id is not None:
            conditions.append(AuditEvent.user_id == user_id)
        if start_at is not None:
            conditions.append(AuditEvent.timestamp >= start_at)
        if end_at is not None:
            conditions.append(AuditEvent.timestamp <= end_at)

        count = self.db.scalar(select(func.count(AuditEvent.id)).where(*conditions))
        statement = (
            select(AuditEvent)
            .where(*conditions)
            .order_by(AuditEvent.timestamp.desc(), AuditEvent.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = list(self.db.scalars(statement).all())
        return rows, int(count or 0)
