# mypy: ignore-errors
"""Add tenant-scoped customer feedback, lifecycle history and product roadmap."""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "b2f70c1d8e43"
down_revision: Union[str, Sequence[str], None] = "63b1a9e2c407"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "product_roadmap_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=24),
            server_default="PROPOSED",
            nullable=False,
        ),
        sa.Column(
            "visibility",
            sa.String(length=16),
            server_default="INTERNAL",
            nullable=False,
        ),
        sa.Column("target_release", sa.String(length=80), nullable=True),
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
            "status IN ('PROPOSED', 'PLANNED', 'IN_PROGRESS', 'SHIPPED', 'DECLINED')",
            name="ck_product_roadmap_items_status",
        ),
        sa.CheckConstraint(
            "visibility IN ('PUBLIC', 'INTERNAL')",
            name="ck_product_roadmap_items_visibility",
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_product_roadmap_items_visibility_status",
        "product_roadmap_items",
        ["visibility", "status"],
    )

    op.create_table(
        "customer_feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("category", sa.String(length=24), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "priority",
            sa.String(length=16),
            server_default="MEDIUM",
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=24),
            server_default="SUBMITTED",
            nullable=False,
        ),
        sa.Column("submitted_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("roadmap_item_id", postgresql.UUID(as_uuid=True), nullable=True),
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
            "category IN ('FEATURE_REQUEST', 'IMPROVEMENT', 'PROBLEM', 'COMPLAINT')",
            name="ck_customer_feedback_category",
        ),
        sa.CheckConstraint(
            "priority IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')",
            name="ck_customer_feedback_priority",
        ),
        sa.CheckConstraint(
            "status IN ('SUBMITTED', 'UNDER_REVIEW', 'ACCEPTED', 'PLANNED', "
            "'IN_PROGRESS', 'COMPLETED', 'DECLINED', 'DUPLICATE')",
            name="ck_customer_feedback_status",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["submitted_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["roadmap_item_id"],
            ["product_roadmap_items.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "tenant_id", name="uq_customer_feedback_id_tenant"),
    )
    op.create_index(
        "ix_customer_feedback_tenant_id", "customer_feedback", ["tenant_id"]
    )
    op.create_index(
        "ix_customer_feedback_submitted_by", "customer_feedback", ["submitted_by"]
    )
    op.create_index(
        "ix_customer_feedback_roadmap_item_id",
        "customer_feedback",
        ["roadmap_item_id"],
    )
    op.create_index(
        "ix_customer_feedback_tenant_created",
        "customer_feedback",
        ["tenant_id", "created_at"],
    )
    op.create_index(
        "ix_customer_feedback_tenant_status",
        "customer_feedback",
        ["tenant_id", "status"],
    )
    op.create_index(
        "ix_customer_feedback_category_priority",
        "customer_feedback",
        ["category", "priority"],
    )

    op.create_table(
        "customer_feedback_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("feedback_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("old_value", sa.String(length=500), nullable=True),
        sa.Column("new_value", sa.String(length=500), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("changed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["changed_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["feedback_id", "tenant_id"],
            ["customer_feedback.id", "customer_feedback.tenant_id"],
            name="fk_customer_feedback_history_feedback_tenant",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_customer_feedback_history_tenant_id",
        "customer_feedback_history",
        ["tenant_id"],
    )
    op.create_index(
        "ix_customer_feedback_history_feedback_created",
        "customer_feedback_history",
        ["feedback_id", "created_at"],
    )
    op.create_index(
        "ix_customer_feedback_history_tenant_created",
        "customer_feedback_history",
        ["tenant_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_customer_feedback_history_tenant_created",
        table_name="customer_feedback_history",
    )
    op.drop_index(
        "ix_customer_feedback_history_feedback_created",
        table_name="customer_feedback_history",
    )
    op.drop_index(
        "ix_customer_feedback_history_tenant_id",
        table_name="customer_feedback_history",
    )
    op.drop_table("customer_feedback_history")

    op.drop_index(
        "ix_customer_feedback_category_priority", table_name="customer_feedback"
    )
    op.drop_index("ix_customer_feedback_tenant_status", table_name="customer_feedback")
    op.drop_index("ix_customer_feedback_tenant_created", table_name="customer_feedback")
    op.drop_index(
        "ix_customer_feedback_roadmap_item_id", table_name="customer_feedback"
    )
    op.drop_index("ix_customer_feedback_submitted_by", table_name="customer_feedback")
    op.drop_index("ix_customer_feedback_tenant_id", table_name="customer_feedback")
    op.drop_table("customer_feedback")

    op.drop_index(
        "ix_product_roadmap_items_visibility_status",
        table_name="product_roadmap_items",
    )
    op.drop_table("product_roadmap_items")
