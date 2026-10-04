import uuid
from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class WorkflowAuditLog(Base):
    __tablename__ = "workflow_audit_logs"

    __table_args__ = (
        Index(
            "ix_workflow_audit_logs_workflow_created",
            "workflow_id",
            "created_at",
        ),
        Index(
            "ix_workflow_audit_logs_user_id",
            "user_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # This is the WorkflowExecution ID.
    workflow_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "workflow_executions.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    step_name: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    action: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    old_status: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    new_status: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    user_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    comments: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    workflow_execution = relationship(
        "WorkflowExecution",
        back_populates="audit_logs",
    )

    user = relationship(
        "User",
        foreign_keys=[user_id],
    )
