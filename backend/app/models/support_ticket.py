"""Tenant-owned customer support tickets, comments, files and audit history."""

import uuid
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.data_protection import EncryptedString
from app.core.database import Base


class SupportTicket(Base):
    """A tenant-owned support request; platform Support Agents may serve tenants."""

    __tablename__ = "support_tickets"
    __table_args__ = (
        UniqueConstraint("id", "tenant_id", name="uq_support_tickets_id_tenant"),
        CheckConstraint(
            "category IN ('API_ISSUE', 'INTEGRATION_PROBLEM', 'SYSTEM_ERROR', "
            "'CONFIGURATION_REQUEST', 'USER_ACCESS_REQUEST', "
            "'REPORTING_REQUEST', 'OTHER')",
            name="ck_support_tickets_category",
        ),
        CheckConstraint(
            "priority IN ('LOW', 'MEDIUM', 'HIGH', 'URGENT')",
            name="ck_support_tickets_priority",
        ),
        CheckConstraint(
            "status IN ('OPEN', 'ASSIGNED', 'IN_PROGRESS', 'WAITING_CUSTOMER', "
            "'RESOLVED', 'CLOSED')",
            name="ck_support_tickets_status",
        ),
        Index(
            "ix_support_tickets_tenant_status_created",
            "tenant_id",
            "status",
            "created_at",
        ),
        Index("ix_support_tickets_assigned_status", "assigned_to", "status"),
        Index("ix_support_tickets_creator_created", "created_by", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(
        String(40), nullable=False, default="OTHER", server_default="OTHER"
    )
    priority: Mapped[str] = mapped_column(
        String(16), nullable=False, default="MEDIUM", server_default="MEDIUM"
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="OPEN", server_default="OPEN"
    )
    assigned_to: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_by: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    @property
    def resolution_time_seconds(self) -> int | None:
        """Elapsed seconds from creation to the current resolution timestamp."""
        if self.resolved_at is None or self.created_at is None:
            return None
        created_at = self.created_at
        resolved_at = self.resolved_at
        if created_at.tzinfo is None and resolved_at.tzinfo is not None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        elif created_at.tzinfo is not None and resolved_at.tzinfo is None:
            resolved_at = resolved_at.replace(tzinfo=timezone.utc)
        return max(0, int((resolved_at - created_at).total_seconds()))


class SupportTicketComment(Base):
    """A public reply or a staff-only internal note on a ticket."""

    __tablename__ = "support_ticket_comments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["ticket_id", "tenant_id"],
            ["support_tickets.id", "support_tickets.tenant_id"],
            name="fk_support_ticket_comments_ticket_tenant",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "length(trim(body)) > 0",
            name="ck_support_ticket_comments_body",
        ),
        Index("ix_support_ticket_comments_ticket_created", "ticket_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ticket_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=False
    )
    author_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_internal: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SupportTicketAttachment(Base):
    """Metadata for a file stored through the configured storage abstraction."""

    __tablename__ = "support_ticket_attachments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["ticket_id", "tenant_id"],
            ["support_tickets.id", "support_tickets.tenant_id"],
            name="fk_support_ticket_attachments_ticket_tenant",
            ondelete="CASCADE",
        ),
        CheckConstraint("file_size > 0", name="ck_support_ticket_attachments_size"),
        Index(
            "ix_support_ticket_attachments_ticket_created", "ticket_id", "created_at"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ticket_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=False
    )
    original_filename: Mapped[str] = mapped_column(EncryptedString(), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    uploaded_by: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SupportTicketHistory(Base):
    """Append-only event stream for status, assignment, comment and file actions."""

    __tablename__ = "support_ticket_history"
    __table_args__ = (
        ForeignKeyConstraint(
            ["ticket_id", "tenant_id"],
            ["support_tickets.id", "support_tickets.tenant_id"],
            name="fk_support_ticket_history_ticket_tenant",
            ondelete="CASCADE",
        ),
        Index("ix_support_ticket_history_ticket_created", "ticket_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ticket_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=False
    )
    actor_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    previous_value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    new_value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
