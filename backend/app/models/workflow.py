import uuid
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.utils.enums import (
    SLAStatus,
    WorkflowExecutionStatus,
    WorkflowStatus,
    WorkflowStepExecutionStatus,
)


class Workflow(Base):
    __tablename__ = "workflows"

    __table_args__ = (
        UniqueConstraint(
            "name",
            name="uq_workflows_name",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        index=True,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    status: Mapped[WorkflowStatus] = mapped_column(
        Enum(
            WorkflowStatus,
            name="workflow_status",
        ),
        nullable=False,
        default=WorkflowStatus.DRAFT,
        server_default=WorkflowStatus.DRAFT.value,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    steps = relationship(
        "WorkflowStep",
        back_populates="workflow",
        cascade="all, delete-orphan",
        order_by="WorkflowStep.order_number",
    )

    executions = relationship(
        "WorkflowExecution",
        back_populates="workflow",
    )


class WorkflowStep(Base):
    __tablename__ = "workflow_steps"

    __table_args__ = (
        UniqueConstraint(
            "workflow_id",
            "order_number",
            name="uq_workflow_steps_workflow_order",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    workflow_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "workflows.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    order_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    assigned_role: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    workflow = relationship(
        "Workflow",
        back_populates="steps",
    )

    executions = relationship(
        "WorkflowStepExecution",
        back_populates="workflow_step",
    )


class WorkflowExecution(Base):
    __tablename__ = "workflow_executions"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    workflow_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "workflows.id",
        ),
        nullable=False,
        index=True,
    )

    entity_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    entity_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        nullable=False,
        index=True,
    )

    status: Mapped[WorkflowExecutionStatus] = mapped_column(
        Enum(
            WorkflowExecutionStatus,
            name="workflow_execution_status",
        ),
        nullable=False,
        default=WorkflowExecutionStatus.IN_PROGRESS,
        server_default=WorkflowExecutionStatus.IN_PROGRESS.value,
        index=True,
    )

    current_step_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "workflow_steps.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    started_by: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    context: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    due_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    sla_status: Mapped[SLAStatus | None] = mapped_column(
        Enum(
            SLAStatus,
            name="sla_status",
        ),
        nullable=True,
        index=True,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    workflow = relationship(
        "Workflow",
        back_populates="executions",
    )

    current_step = relationship(
        "WorkflowStep",
        foreign_keys=[current_step_id],
    )

    started_by_user = relationship(
        "User",
        foreign_keys=[started_by],
    )

    step_executions = relationship(
        "WorkflowStepExecution",
        back_populates="workflow_execution",
        cascade="all, delete-orphan",
        order_by="WorkflowStepExecution.order_number",
    )

    audit_logs = relationship(
        "WorkflowAuditLog",
        back_populates="workflow_execution",
        cascade="all, delete-orphan",
        order_by="WorkflowAuditLog.created_at",
    )


class WorkflowStepExecution(Base):
    __tablename__ = "workflow_step_executions"

    __table_args__ = (
        UniqueConstraint(
            "workflow_execution_id",
            "workflow_step_id",
            name="uq_workflow_step_execution",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    workflow_execution_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "workflow_executions.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    workflow_step_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "workflow_steps.id",
        ),
        nullable=False,
        index=True,
    )

    # Snapshot the definition so historical executions remain
    # understandable if the workflow is later changed.
    step_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    order_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    assigned_role: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    status: Mapped[WorkflowStepExecutionStatus] = mapped_column(
        Enum(
            WorkflowStepExecutionStatus,
            name="workflow_step_execution_status",
        ),
        nullable=False,
        default=WorkflowStepExecutionStatus.PENDING,
        server_default=WorkflowStepExecutionStatus.PENDING.value,
        index=True,
    )

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    result: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    workflow_execution = relationship(
        "WorkflowExecution",
        back_populates="step_executions",
    )

    workflow_step = relationship(
        "WorkflowStep",
        back_populates="executions",
    )
