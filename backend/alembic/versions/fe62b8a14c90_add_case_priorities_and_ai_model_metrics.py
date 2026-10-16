# mypy: ignore-errors
"""Add explainable compliance case priorities and AI model monitoring.

Revision ID: fe62b8a14c90
Revises: d2a0c5b7e913
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "fe62b8a14c90"
down_revision: Union[str, Sequence[str], None] = "d2a0c5b7e913"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    case_priority = postgresql.ENUM(
        "LOW",
        "MEDIUM",
        "HIGH",
        "CRITICAL",
        name="compliance_case_priority",
        create_type=False,
    )

    op.create_table(
        "case_priorities",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("priority_level", case_priority, nullable=False),
        sa.Column("priority_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "risk_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "priority_score >= 0 AND priority_score <= 100",
            name="ck_case_priorities_score_range",
        ),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["compliance_cases.id"],
            name="fk_case_priorities_case_id_compliance_cases",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_case_priorities_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_case_priorities"),
    )
    op.create_index("ix_case_priorities_tenant_id", "case_priorities", ["tenant_id"])
    op.create_index("ix_case_priorities_case_id", "case_priorities", ["case_id"])
    op.create_index(
        "ix_case_priorities_priority_level",
        "case_priorities",
        ["priority_level"],
    )
    op.create_index("ix_case_priorities_created_at", "case_priorities", ["created_at"])
    op.create_index(
        "ix_case_priorities_tenant_case_created",
        "case_priorities",
        ["tenant_id", "case_id", "created_at"],
    )
    op.create_index(
        "ix_case_priorities_tenant_level_score",
        "case_priorities",
        ["tenant_id", "priority_level", "priority_score"],
    )

    op.create_table(
        "ai_model_metrics",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model_name", sa.String(length=200), nullable=False),
        sa.Column(
            "model_version",
            sa.String(length=100),
            server_default="unspecified",
            nullable=False,
        ),
        sa.Column("request_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("success_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "total_response_time_ms",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column("feedback_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "feedback_rating_sum", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column(
            "positive_feedback_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "accuracy_measurement_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "correct_prediction_count",
            sa.Integer(),
            server_default="0",
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
        sa.CheckConstraint(
            "request_count >= 0",
            name="ck_ai_model_metrics_request_count_nonnegative",
        ),
        sa.CheckConstraint(
            "success_count >= 0",
            name="ck_ai_model_metrics_success_count_nonnegative",
        ),
        sa.CheckConstraint(
            "error_count >= 0",
            name="ck_ai_model_metrics_error_count_nonnegative",
        ),
        sa.CheckConstraint(
            "total_response_time_ms >= 0",
            name="ck_ai_model_metrics_total_latency_nonnegative",
        ),
        sa.CheckConstraint(
            "feedback_count >= 0",
            name="ck_ai_model_metrics_feedback_count_nonnegative",
        ),
        sa.CheckConstraint(
            "accuracy_measurement_count >= 0",
            name="ck_ai_model_metrics_accuracy_count_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_ai_model_metrics_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ai_model_metrics"),
        sa.UniqueConstraint(
            "tenant_id",
            "model_name",
            "model_version",
            name="uq_ai_model_metrics_tenant_model_version",
        ),
    )
    op.create_index("ix_ai_model_metrics_tenant_id", "ai_model_metrics", ["tenant_id"])
    op.create_index(
        "ix_ai_model_metrics_model_name", "ai_model_metrics", ["model_name"]
    )
    op.create_index(
        "ix_ai_model_metrics_tenant_updated",
        "ai_model_metrics",
        ["tenant_id", "updated_at"],
    )

    op.create_table(
        "ai_model_feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("interaction_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model_name", sa.String(length=200), nullable=False),
        sa.Column(
            "model_version",
            sa.String(length=100),
            server_default="unspecified",
            nullable=False,
        ),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("is_accurate", sa.Boolean(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "rating >= 1 AND rating <= 5",
            name="ck_ai_model_feedback_rating_range",
        ),
        sa.ForeignKeyConstraint(
            ["interaction_id"],
            ["ai_interactions.id"],
            name="fk_ai_model_feedback_interaction_id_ai_interactions",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_ai_model_feedback_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_ai_model_feedback_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ai_model_feedback"),
        sa.UniqueConstraint(
            "tenant_id",
            "interaction_id",
            "user_id",
            name="uq_ai_model_feedback_tenant_interaction_user",
        ),
    )
    op.create_index(
        "ix_ai_model_feedback_tenant_id", "ai_model_feedback", ["tenant_id"]
    )
    op.create_index(
        "ix_ai_model_feedback_interaction_id",
        "ai_model_feedback",
        ["interaction_id"],
    )
    op.create_index("ix_ai_model_feedback_user_id", "ai_model_feedback", ["user_id"])
    op.create_index(
        "ix_ai_model_feedback_tenant_created",
        "ai_model_feedback",
        ["tenant_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_ai_model_feedback_tenant_created", table_name="ai_model_feedback")
    op.drop_index("ix_ai_model_feedback_user_id", table_name="ai_model_feedback")
    op.drop_index("ix_ai_model_feedback_interaction_id", table_name="ai_model_feedback")
    op.drop_index("ix_ai_model_feedback_tenant_id", table_name="ai_model_feedback")
    op.drop_table("ai_model_feedback")

    op.drop_index("ix_ai_model_metrics_tenant_updated", table_name="ai_model_metrics")
    op.drop_index("ix_ai_model_metrics_model_name", table_name="ai_model_metrics")
    op.drop_index("ix_ai_model_metrics_tenant_id", table_name="ai_model_metrics")
    op.drop_table("ai_model_metrics")

    op.drop_index("ix_case_priorities_tenant_level_score", table_name="case_priorities")
    op.drop_index(
        "ix_case_priorities_tenant_case_created", table_name="case_priorities"
    )
    op.drop_index("ix_case_priorities_created_at", table_name="case_priorities")
    op.drop_index("ix_case_priorities_priority_level", table_name="case_priorities")
    op.drop_index("ix_case_priorities_case_id", table_name="case_priorities")
    op.drop_index("ix_case_priorities_tenant_id", table_name="case_priorities")
    op.drop_table("case_priorities")
