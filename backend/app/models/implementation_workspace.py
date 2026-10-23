"""
Enterprise implementation workspace, milestones, tasks, collaborators, and comments.
"""

import uuid
from datetime import date, datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.utils.implementation_workspace_enums import (
    ImplementationStage,
    ImplementationWorkStatus,
)


class ImplementationWorkspace(Base):
    """A customer-specific implementation plan shared by customer and internal teams.

    ``tenant_id`` is the creating team's tenant for tenant ownership enforcement.
    ``customer_tenant_id`` identifies the enterprise customer being implemented.
    Collaborator access is explicitly controlled through workspace membership.
    """

    __tablename__ = "implementation_workspaces"
    __table_args__ = (
        CheckConstraint(
            (
                "status IN ('NOT_STARTED', 'CONFIGURATION', 'INTEGRATION', "
                "'TESTING', 'READY_FOR_PRODUCTION')"
            ),
            name="ck_implementation_workspaces_status",
        ),
        CheckConstraint(
            (
                "api_setup_status IN ('NOT_STARTED', 'IN_PROGRESS', "
                "'COMPLETED', 'BLOCKED')"
            ),
            name="ck_implementation_workspaces_api_setup_status",
        ),
        CheckConstraint(
            (
                "integration_status IN ('NOT_STARTED', "
                "'IN_PROGRESS', 'COMPLETED', 'BLOCKED')"
            ),
            name="ck_implementation_workspaces_integration_status",
        ),
        CheckConstraint(
            "testing_status IN ('NOT_STARTED', 'IN_PROGRESS', 'COMPLETED', 'BLOCKED')",
            name="ck_implementation_workspaces_testing_status",
        ),
        CheckConstraint(
            "training_status IN ('NOT_STARTED', 'IN_PROGRESS', 'COMPLETED', 'BLOCKED')",
            name="ck_implementation_workspaces_training_status",
        ),
        CheckConstraint(
            (
                "user_acceptance_testing_status IN "
                "('NOT_STARTED', 'IN_PROGRESS', 'COMPLETED', 'BLOCKED')"
            ),
            name="ck_implementation_workspaces_uat_status",
        ),
        CheckConstraint(
            (
                "go_live_readiness_status IN "
                "('NOT_STARTED', 'IN_PROGRESS', 'COMPLETED', 'BLOCKED')"
            ),
            name="ck_implementation_workspaces_go_live_status",
        ),
        Index(
            "ix_implementation_workspaces_customer_status",
            "customer_tenant_id",
            "status",
        ),
        Index(
            "ix_implementation_workspaces_owner_created",
            "tenant_id",
            "created_at",
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
    customer_tenant_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=ImplementationStage.NOT_STARTED.value,
        server_default=ImplementationStage.NOT_STARTED.value,
    )
    api_setup_status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default=ImplementationWorkStatus.NOT_STARTED.value,
        server_default=ImplementationWorkStatus.NOT_STARTED.value,
    )
    integration_status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default=ImplementationWorkStatus.NOT_STARTED.value,
        server_default=ImplementationWorkStatus.NOT_STARTED.value,
    )
    testing_status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default=ImplementationWorkStatus.NOT_STARTED.value,
        server_default=ImplementationWorkStatus.NOT_STARTED.value,
    )
    training_status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default=ImplementationWorkStatus.NOT_STARTED.value,
        server_default=ImplementationWorkStatus.NOT_STARTED.value,
    )
    user_acceptance_testing_status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default=ImplementationWorkStatus.NOT_STARTED.value,
        server_default=ImplementationWorkStatus.NOT_STARTED.value,
    )
    go_live_readiness_status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default=ImplementationWorkStatus.NOT_STARTED.value,
        server_default=ImplementationWorkStatus.NOT_STARTED.value,
    )
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    target_go_live_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_go_live_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    members: Mapped[list["ImplementationWorkspaceMember"]] = relationship(
        back_populates="workspace",
        cascade="all, delete-orphan",
        order_by="ImplementationWorkspaceMember.created_at",
    )
    milestones: Mapped[list["ImplementationWorkspaceMilestone"]] = relationship(
        back_populates="workspace",
        cascade="all, delete-orphan",
        order_by="ImplementationWorkspaceMilestone.created_at",
    )
    tasks: Mapped[list["ImplementationWorkspaceTask"]] = relationship(
        back_populates="workspace",
        cascade="all, delete-orphan",
        order_by="ImplementationWorkspaceTask.created_at",
    )
    comments: Mapped[list["ImplementationWorkspaceComment"]] = relationship(
        back_populates="workspace",
        cascade="all, delete-orphan",
        order_by="ImplementationWorkspaceComment.created_at",
    )

    @property
    def progress_percent(self) -> int:
        """Percentage of workspace tasks marked completed; 0 when there are no tasks."""
        if not self.tasks:
            return 0
        completed = sum(
            task.status == ImplementationWorkStatus.COMPLETED.value
            for task in self.tasks
        )
        return round(completed * 100 / len(self.tasks))


class ImplementationWorkspaceMember(Base):
    """User granted access to an implementation workspace."""

    __tablename__ = "implementation_workspace_members"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "user_id", name="uq_implementation_workspace_member"
        ),
        CheckConstraint(
            "member_type IN ('INTERNAL', 'CUSTOMER')",
            name="ck_implementation_workspace_members_type",
        ),
        CheckConstraint(
            "role IN ('MANAGER', 'MEMBER', 'VIEWER')",
            name="ck_implementation_workspace_members_role",
        ),
        Index("ix_implementation_workspace_members_user", "user_id", "workspace_id"),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("implementation_workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    member_type: Mapped[str] = mapped_column(String(16), nullable=False)
    role: Mapped[str] = mapped_column(
        String(16), nullable=False, default="MEMBER", server_default="MEMBER"
    )
    invited_by: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    workspace: Mapped[ImplementationWorkspace] = relationship(back_populates="members")
    user = relationship("User", foreign_keys=[user_id])
    inviter = relationship("User", foreign_keys=[invited_by])


class ImplementationWorkspaceMilestone(Base):
    """A dated checkpoint in the implementation timeline."""

    __tablename__ = "implementation_workspace_milestones"
    __table_args__ = (
        CheckConstraint(
            "status IN ('NOT_STARTED', 'IN_PROGRESS', 'COMPLETED', 'BLOCKED')",
            name="ck_implementation_workspace_milestones_status",
        ),
        Index(
            "ix_implementation_workspace_milestones_workspace_due",
            "workspace_id",
            "due_date",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("implementation_workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default=ImplementationWorkStatus.NOT_STARTED.value,
        server_default=ImplementationWorkStatus.NOT_STARTED.value,
    )
    assigned_to: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_by: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    workspace: Mapped[ImplementationWorkspace] = relationship(
        back_populates="milestones"
    )
    assigned_user = relationship("User", foreign_keys=[assigned_to])


class ImplementationWorkspaceTask(Base):
    """Actionable project, technical, or business task within a workspace."""

    __tablename__ = "implementation_workspace_tasks"
    __table_args__ = (
        CheckConstraint(
            "category IN ('PROJECT', 'TECHNICAL', 'BUSINESS')",
            name="ck_implementation_workspace_tasks_category",
        ),
        CheckConstraint(
            "status IN ('NOT_STARTED', 'IN_PROGRESS', 'COMPLETED', 'BLOCKED')",
            name="ck_implementation_workspace_tasks_status",
        ),
        CheckConstraint(
            "priority IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')",
            name="ck_implementation_workspace_tasks_priority",
        ),
        Index(
            "ix_implementation_workspace_tasks_workspace_status",
            "workspace_id",
            "status",
        ),
        Index(
            "ix_implementation_workspace_tasks_workspace_category",
            "workspace_id",
            "category",
        ),
        Index("ix_implementation_workspace_tasks_assigned", "assigned_to", "status"),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("implementation_workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    milestone_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("implementation_workspace_milestones.id", ondelete="SET NULL"),
        nullable=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(
        String(16), nullable=False, default="PROJECT", server_default="PROJECT"
    )
    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default=ImplementationWorkStatus.NOT_STARTED.value,
        server_default=ImplementationWorkStatus.NOT_STARTED.value,
    )
    priority: Mapped[str] = mapped_column(
        String(16), nullable=False, default="MEDIUM", server_default="MEDIUM"
    )
    assigned_to: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_by: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    workspace: Mapped[ImplementationWorkspace] = relationship(back_populates="tasks")
    milestone = relationship("ImplementationWorkspaceMilestone")
    assigned_user = relationship("User", foreign_keys=[assigned_to])


class ImplementationWorkspaceComment(Base):
    """Collaboration comment attached to a workspace or one of its tasks."""

    __tablename__ = "implementation_workspace_comments"
    __table_args__ = (
        Index(
            "ix_implementation_workspace_comments_workspace_created",
            "workspace_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("implementation_workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    task_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("implementation_workspace_tasks.id", ondelete="CASCADE"),
        nullable=True,
    )
    author_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    workspace: Mapped[ImplementationWorkspace] = relationship(back_populates="comments")
    task = relationship("ImplementationWorkspaceTask")
    author = relationship("User", foreign_keys=[author_id])
