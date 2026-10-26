# mypy: ignore-errors
"""Create tenant-isolated support tickets, replies, attachments and history."""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "e2f1c4b8a907"
down_revision: Union[str, Sequence[str], None] = "d9e4a8b7c612"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "support_tickets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category", sa.String(40), server_default="OTHER", nullable=False),
        sa.Column("priority", sa.String(16), server_default="MEDIUM", nullable=False),
        sa.Column("status", sa.String(30), server_default="OPEN", nullable=False),
        sa.Column("assigned_to", postgresql.UUID(as_uuid=True), nullable=True),
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
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "category IN ('API_ISSUE', 'INTEGRATION_PROBLEM', 'SYSTEM_ERROR', "
            "'CONFIGURATION_REQUEST', 'USER_ACCESS_REQUEST', "
            "'REPORTING_REQUEST', 'OTHER')",
            name="ck_support_tickets_category",
        ),
        sa.CheckConstraint(
            "priority IN ('LOW', 'MEDIUM', 'HIGH', 'URGENT')",
            name="ck_support_tickets_priority",
        ),
        sa.CheckConstraint(
            "status IN ('OPEN', 'ASSIGNED', 'IN_PROGRESS', "
            "'WAITING_CUSTOMER', 'RESOLVED', 'CLOSED')",
            name="ck_support_tickets_status",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assigned_to"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "tenant_id", name="uq_support_tickets_id_tenant"),
    )
    op.create_index("ix_support_tickets_tenant_id", "support_tickets", ["tenant_id"])
    op.create_index(
        "ix_support_tickets_assigned_to", "support_tickets", ["assigned_to"]
    )
    op.create_index("ix_support_tickets_created_by", "support_tickets", ["created_by"])
    op.create_index(
        "ix_support_tickets_tenant_status_created",
        "support_tickets",
        ["tenant_id", "status", "created_at"],
    )
    op.create_index(
        "ix_support_tickets_assigned_status",
        "support_tickets",
        ["assigned_to", "status"],
    )
    op.create_index(
        "ix_support_tickets_creator_created",
        "support_tickets",
        ["created_by", "created_at"],
    )

    op.create_table(
        "support_ticket_comments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticket_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("author_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "is_internal", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(trim(body)) > 0",
            name="ck_support_ticket_comments_body",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["ticket_id", "tenant_id"],
            ["support_tickets.id", "support_tickets.tenant_id"],
            name="fk_support_ticket_comments_ticket_tenant",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_support_ticket_comments_tenant_id",
        "support_ticket_comments",
        ["tenant_id"],
    )
    op.create_index(
        "ix_support_ticket_comments_author_id",
        "support_ticket_comments",
        ["author_id"],
    )
    op.create_index(
        "ix_support_ticket_comments_ticket_created",
        "support_ticket_comments",
        ["ticket_id", "created_at"],
    )

    op.create_table(
        "support_ticket_attachments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticket_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("original_filename", sa.Text(), nullable=False),
        sa.Column("storage_path", sa.String(500), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("file_size > 0", name="ck_support_ticket_attachments_size"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["ticket_id", "tenant_id"],
            ["support_tickets.id", "support_tickets.tenant_id"],
            name="fk_support_ticket_attachments_ticket_tenant",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_support_ticket_attachments_tenant_id",
        "support_ticket_attachments",
        ["tenant_id"],
    )
    op.create_index(
        "ix_support_ticket_attachments_uploaded_by",
        "support_ticket_attachments",
        ["uploaded_by"],
    )
    op.create_index(
        "ix_support_ticket_attachments_ticket_created",
        "support_ticket_attachments",
        ["ticket_id", "created_at"],
    )

    op.create_table(
        "support_ticket_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticket_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("previous_value", sa.String(255), nullable=True),
        sa.Column("new_value", sa.String(255), nullable=True),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["ticket_id", "tenant_id"],
            ["support_tickets.id", "support_tickets.tenant_id"],
            name="fk_support_ticket_history_ticket_tenant",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_support_ticket_history_tenant_id", "support_ticket_history", ["tenant_id"]
    )
    op.create_index(
        "ix_support_ticket_history_actor_id", "support_ticket_history", ["actor_id"]
    )
    op.create_index(
        "ix_support_ticket_history_ticket_created",
        "support_ticket_history",
        ["ticket_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_support_ticket_history_ticket_created",
        table_name="support_ticket_history",
    )
    op.drop_index(
        "ix_support_ticket_history_actor_id", table_name="support_ticket_history"
    )
    op.drop_index(
        "ix_support_ticket_history_tenant_id", table_name="support_ticket_history"
    )
    op.drop_table("support_ticket_history")
    op.drop_index(
        "ix_support_ticket_attachments_ticket_created",
        table_name="support_ticket_attachments",
    )
    op.drop_index(
        "ix_support_ticket_attachments_uploaded_by",
        table_name="support_ticket_attachments",
    )
    op.drop_index(
        "ix_support_ticket_attachments_tenant_id",
        table_name="support_ticket_attachments",
    )
    op.drop_table("support_ticket_attachments")
    op.drop_index(
        "ix_support_ticket_comments_ticket_created",
        table_name="support_ticket_comments",
    )
    op.drop_index(
        "ix_support_ticket_comments_author_id",
        table_name="support_ticket_comments",
    )
    op.drop_index(
        "ix_support_ticket_comments_tenant_id",
        table_name="support_ticket_comments",
    )
    op.drop_table("support_ticket_comments")
    op.drop_index("ix_support_tickets_creator_created", table_name="support_tickets")
    op.drop_index("ix_support_tickets_assigned_status", table_name="support_tickets")
    op.drop_index(
        "ix_support_tickets_tenant_status_created", table_name="support_tickets"
    )
    op.drop_index("ix_support_tickets_created_by", table_name="support_tickets")
    op.drop_index("ix_support_tickets_assigned_to", table_name="support_tickets")
    op.drop_index("ix_support_tickets_tenant_id", table_name="support_tickets")
    op.drop_table("support_tickets")
