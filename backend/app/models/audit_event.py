"""Append-only, tenant-aware audit evidence for regulated workflows."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, String, event, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AuditEvent(Base):
    """A durable audit event. IDs are intentionally not FK-cascaded to users/tenants."""

    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_tenant_timestamp", "tenant_id", "timestamp"),
        Index(
            "ix_audit_events_tenant_action_timestamp",
            "tenant_id",
            "action",
            "timestamp",
        ),
        Index("ix_audit_events_tenant_entity", "tenant_id", "entity_type", "entity_id"),
        Index(
            "ix_audit_events_tenant_user_timestamp",
            "tenant_id",
            "user_id",
            "timestamp",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Nullable for unknown-user login attempts or platform-level events. No FK is
    # intentional: deleting a tenant/user must not delete historical audit evidence.
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
    # SQLAlchemy reserves the declarative attribute name `metadata`; map the DB
    # column `metadata` to the Python attribute `event_metadata`.
    event_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )


def _reject_mutation(mapper: Any, connection: Any, target: AuditEvent) -> None:
    raise ValueError("AuditEvent records are append-only and cannot be modified")


event.listen(AuditEvent, "before_update", _reject_mutation)
event.listen(AuditEvent, "before_delete", _reject_mutation)
