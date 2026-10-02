import uuid
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
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
from app.utils.enums import TaskAssignmentStrategy


class TaskAssignmentRule(Base):
    __tablename__ = "task_assignment_rules"

    __table_args__ = (
        UniqueConstraint(
            "name",
            name="uq_task_assignment_rules_name",
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

    workflow_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "workflows.id",
            ondelete="CASCADE",
        ),
        nullable=True,
        index=True,
    )

    workflow_step_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "workflow_steps.id",
            ondelete="CASCADE",
        ),
        nullable=True,
        index=True,
    )

    conditions: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    strategy: Mapped[TaskAssignmentStrategy] = mapped_column(
        Enum(
            TaskAssignmentStrategy,
            name="task_assignment_strategy",
        ),
        nullable=False,
        default=TaskAssignmentStrategy.LEAST_LOADED,
        server_default=TaskAssignmentStrategy.LEAST_LOADED.value,
    )

    priority: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=100,
        server_default="100",
        index=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        index=True,
    )

    created_by: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
        ),
        nullable=True,
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

    workflow = relationship(
        "Workflow",
        foreign_keys=[workflow_id],
    )

    workflow_step = relationship(
        "WorkflowStep",
        foreign_keys=[workflow_step_id],
    )

    created_by_user = relationship(
        "User",
        foreign_keys=[created_by],
    )
