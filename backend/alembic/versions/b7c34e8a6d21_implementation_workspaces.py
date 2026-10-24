# mypy: ignore-errors
"""Create collaborative enterprise implementation workspaces."""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "b7c34e8a6d21"
down_revision: Union[str, Sequence[str], None] = "f8c0a1b2d3e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "implementation_workspaces",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status", sa.String(length=32), server_default="NOT_STARTED", nullable=False
        ),
        sa.Column(
            "api_setup_status",
            sa.String(length=24),
            server_default="NOT_STARTED",
            nullable=False,
        ),
        sa.Column(
            "integration_status",
            sa.String(length=24),
            server_default="NOT_STARTED",
            nullable=False,
        ),
        sa.Column(
            "testing_status",
            sa.String(length=24),
            server_default="NOT_STARTED",
            nullable=False,
        ),
        sa.Column(
            "training_status",
            sa.String(length=24),
            server_default="NOT_STARTED",
            nullable=False,
        ),
        sa.Column(
            "user_acceptance_testing_status",
            sa.String(length=24),
            server_default="NOT_STARTED",
            nullable=False,
        ),
        sa.Column(
            "go_live_readiness_status",
            sa.String(length=24),
            server_default="NOT_STARTED",
            nullable=False,
        ),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("target_go_live_date", sa.Date(), nullable=True),
        sa.Column("actual_go_live_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            (
                "status IN ('NOT_STARTED', 'CONFIGURATION', 'INTEGRATION', "
                "'TESTING', 'READY_FOR_PRODUCTION')"
            ),
            name="ck_implementation_workspaces_status",
        ),
        sa.CheckConstraint(
            (
                "api_setup_status IN ('NOT_STARTED', 'IN_PROGRESS', "
                "'COMPLETED', 'BLOCKED')"
            ),
            name="ck_implementation_workspaces_api_setup_status",
        ),
        sa.CheckConstraint(
            (
                "integration_status IN ('NOT_STARTED', "
                "'IN_PROGRESS', 'COMPLETED', 'BLOCKED')"
            ),
            name="ck_implementation_workspaces_integration_status",
        ),
        sa.CheckConstraint(
            "testing_status IN ('NOT_STARTED', 'IN_PROGRESS', 'COMPLETED', 'BLOCKED')",
            name="ck_implementation_workspaces_testing_status",
        ),
        sa.CheckConstraint(
            "training_status IN ('NOT_STARTED', 'IN_PROGRESS', 'COMPLETED', 'BLOCKED')",
            name="ck_implementation_workspaces_training_status",
        ),
        sa.CheckConstraint(
            (
                "user_acceptance_testing_status IN ('NOT_STARTED', "
                "'IN_PROGRESS', 'COMPLETED', 'BLOCKED')"
            ),
            name="ck_implementation_workspaces_uat_status",
        ),
        sa.CheckConstraint(
            (
                "go_live_readiness_status IN ('NOT_STARTED', "
                "'IN_PROGRESS', 'COMPLETED', 'BLOCKED')"
            ),
            name="ck_implementation_workspaces_go_live_status",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["customer_tenant_id"], ["tenants.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_implementation_workspaces_tenant_id",
        "implementation_workspaces",
        ["tenant_id"],
    )
    op.create_index(
        "ix_implementation_workspaces_customer_tenant_id",
        "implementation_workspaces",
        ["customer_tenant_id"],
    )
    op.create_index(
        "ix_implementation_workspaces_customer_status",
        "implementation_workspaces",
        ["customer_tenant_id", "status"],
    )
    op.create_index(
        "ix_implementation_workspaces_owner_created",
        "implementation_workspaces",
        ["tenant_id", "created_at"],
    )

    op.create_table(
        "implementation_workspace_members",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("member_type", sa.String(length=16), nullable=False),
        sa.Column(
            "role", sa.String(length=16), server_default="MEMBER", nullable=False
        ),
        sa.Column("invited_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "member_type IN ('INTERNAL', 'CUSTOMER')",
            name="ck_implementation_workspace_members_type",
        ),
        sa.CheckConstraint(
            "role IN ('MANAGER', 'MEMBER', 'VIEWER')",
            name="ck_implementation_workspace_members_role",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["implementation_workspaces.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invited_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id", "user_id", name="uq_implementation_workspace_member"
        ),
    )
    op.create_index(
        "ix_implementation_workspace_members_user",
        "implementation_workspace_members",
        ["user_id", "workspace_id"],
    )

    op.create_table(
        "implementation_workspace_milestones",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column(
            "status", sa.String(length=24), server_default="NOT_STARTED", nullable=False
        ),
        sa.Column("assigned_to", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('NOT_STARTED', 'IN_PROGRESS', 'COMPLETED', 'BLOCKED')",
            name="ck_implementation_workspace_milestones_status",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["implementation_workspaces.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["assigned_to"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_implementation_workspace_milestones_workspace_due",
        "implementation_workspace_milestones",
        ["workspace_id", "due_date"],
    )

    op.create_table(
        "implementation_workspace_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("milestone_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "category", sa.String(length=16), server_default="PROJECT", nullable=False
        ),
        sa.Column(
            "status", sa.String(length=24), server_default="NOT_STARTED", nullable=False
        ),
        sa.Column(
            "priority", sa.String(length=16), server_default="MEDIUM", nullable=False
        ),
        sa.Column("assigned_to", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "category IN ('PROJECT', 'TECHNICAL', 'BUSINESS')",
            name="ck_implementation_workspace_tasks_category",
        ),
        sa.CheckConstraint(
            "status IN ('NOT_STARTED', 'IN_PROGRESS', 'COMPLETED', 'BLOCKED')",
            name="ck_implementation_workspace_tasks_status",
        ),
        sa.CheckConstraint(
            "priority IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')",
            name="ck_implementation_workspace_tasks_priority",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["implementation_workspaces.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["milestone_id"],
            ["implementation_workspace_milestones.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["assigned_to"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_implementation_workspace_tasks_workspace_status",
        "implementation_workspace_tasks",
        ["workspace_id", "status"],
    )
    op.create_index(
        "ix_implementation_workspace_tasks_workspace_category",
        "implementation_workspace_tasks",
        ["workspace_id", "category"],
    )
    op.create_index(
        "ix_implementation_workspace_tasks_assigned",
        "implementation_workspace_tasks",
        ["assigned_to", "status"],
    )

    op.create_table(
        "implementation_workspace_comments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("author_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["implementation_workspaces.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["task_id"], ["implementation_workspace_tasks.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_implementation_workspace_comments_workspace_created",
        "implementation_workspace_comments",
        ["workspace_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_implementation_workspace_comments_workspace_created",
        table_name="implementation_workspace_comments",
    )
    op.drop_table("implementation_workspace_comments")
    op.drop_index(
        "ix_implementation_workspace_tasks_assigned",
        table_name="implementation_workspace_tasks",
    )
    op.drop_index(
        "ix_implementation_workspace_tasks_workspace_category",
        table_name="implementation_workspace_tasks",
    )
    op.drop_index(
        "ix_implementation_workspace_tasks_workspace_status",
        table_name="implementation_workspace_tasks",
    )
    op.drop_table("implementation_workspace_tasks")
    op.drop_index(
        "ix_implementation_workspace_milestones_workspace_due",
        table_name="implementation_workspace_milestones",
    )
    op.drop_table("implementation_workspace_milestones")
    op.drop_index(
        "ix_implementation_workspace_members_user",
        table_name="implementation_workspace_members",
    )
    op.drop_table("implementation_workspace_members")
    op.drop_index(
        "ix_implementation_workspaces_owner_created",
        table_name="implementation_workspaces",
    )
    op.drop_index(
        "ix_implementation_workspaces_customer_status",
        table_name="implementation_workspaces",
    )
    op.drop_index(
        "ix_implementation_workspaces_customer_tenant_id",
        table_name="implementation_workspaces",
    )
    op.drop_index(
        "ix_implementation_workspaces_tenant_id", table_name="implementation_workspaces"
    )
    op.drop_table("implementation_workspaces")
