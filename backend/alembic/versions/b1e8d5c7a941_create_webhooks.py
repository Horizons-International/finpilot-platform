# mypy: ignore-errors
"""Create tenant-scoped webhooks and a durable delivery outbox."""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "b1e8d5c7a941"
down_revision: Union[str, Sequence[str], None] = "a7d2f91c4e61"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

webhook_status = postgresql.ENUM(
    "ACTIVE",
    "DISABLED",
    name="webhook_status",
    create_type=False,
)
webhook_delivery_status = postgresql.ENUM(
    "PENDING",
    "DELIVERING",
    "DELIVERED",
    "RETRYING",
    "FAILED",
    name="webhook_delivery_status",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    webhook_status.create(bind, checkfirst=True)
    webhook_delivery_status.create(bind, checkfirst=True)

    op.create_table(
        "webhooks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("endpoint_url", sa.String(length=2048), nullable=False),
        sa.Column("secret_key", sa.Text(), nullable=False),
        sa.Column(
            "event_types", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "status",
            webhook_status,
            server_default="ACTIVE",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_delivery_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_webhooks_tenant_id", "webhooks", ["tenant_id"], unique=False)
    op.create_index("ix_webhooks_status", "webhooks", ["status"], unique=False)

    op.create_table(
        "webhook_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("webhook_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column(
            "status",
            webhook_delivery_status,
            server_default="PENDING",
            nullable=False,
        ),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["webhook_id"], ["webhooks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_webhook_events_tenant_id", "webhook_events", ["tenant_id"], unique=False
    )
    op.create_index(
        "ix_webhook_events_webhook_id", "webhook_events", ["webhook_id"], unique=False
    )
    op.create_index(
        "ix_webhook_events_event_type", "webhook_events", ["event_type"], unique=False
    )
    op.create_index(
        "ix_webhook_events_status", "webhook_events", ["status"], unique=False
    )
    op.create_index(
        "ix_webhook_events_created_at", "webhook_events", ["created_at"], unique=False
    )
    op.create_index(
        "ix_webhook_events_next_attempt_at",
        "webhook_events",
        ["next_attempt_at"],
        unique=False,
    )
    op.create_index(
        "ix_webhook_events_ready",
        "webhook_events",
        ["status", "next_attempt_at"],
        unique=False,
    )
    op.create_index(
        "ix_webhook_events_tenant_created",
        "webhook_events",
        ["tenant_id", "created_at"],
        unique=False,
    )

    # The audit enum is created by the existing audit-log migrations.
    for value in (
        "WEBHOOK_CREATED",
        "WEBHOOK_UPDATED",
        "WEBHOOK_ENABLED",
        "WEBHOOK_DISABLED",
    ):
        op.execute(f"ALTER TYPE auditeventtype ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    op.drop_table("webhook_events")
    op.drop_table("webhooks")
    webhook_delivery_status.drop(op.get_bind(), checkfirst=True)
    webhook_status.drop(op.get_bind(), checkfirst=True)
    # PostgreSQL does not support safely removing individual audit enum values;
    # the WEBHOOK_* audit values are intentionally retained on downgrade.
