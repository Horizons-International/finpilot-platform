# mypy: ignore-errors
"""Store tenant-scoped explanations for AI decisions.

Revision ID: 7d8e91c2a4f6
Revises: fe62b8a14c90
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "7d8e91c2a4f6"
down_revision: Union[str, Sequence[str], None] = "fe62b8a14c90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_decision_explanations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decision_type", sa.String(length=64), nullable=False),
        sa.Column("decision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "factors",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "data_sources",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "risk_indicators",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("confidence_score", sa.Numeric(5, 4), nullable=True),
        sa.Column("recommendation_reason", sa.Text(), nullable=False),
        sa.Column("model_name", sa.String(length=200), nullable=True),
        sa.Column("provider_name", sa.String(length=100), nullable=True),
        sa.Column(
            "decision_snapshot",
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
            "confidence_score IS NULL OR "
            "(confidence_score >= 0 AND confidence_score <= 1)",
            name="ck_ai_decision_explanations_confidence_range",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_ai_decision_explanations_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ai_decision_explanations"),
    )
    op.create_index(
        "ix_ai_decision_explanations_tenant_id",
        "ai_decision_explanations",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_decision_explanations_decision_type",
        "ai_decision_explanations",
        ["decision_type"],
        unique=False,
    )
    op.create_index(
        "ix_ai_decision_explanations_decision_id",
        "ai_decision_explanations",
        ["decision_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_decision_explanations_created_at",
        "ai_decision_explanations",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_ai_decision_explanations_tenant_decision_created",
        "ai_decision_explanations",
        ["tenant_id", "decision_type", "decision_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_ai_decision_explanations_tenant_created",
        "ai_decision_explanations",
        ["tenant_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_decision_explanations_tenant_created",
        table_name="ai_decision_explanations",
    )
    op.drop_index(
        "ix_ai_decision_explanations_tenant_decision_created",
        table_name="ai_decision_explanations",
    )
    op.drop_index(
        "ix_ai_decision_explanations_created_at",
        table_name="ai_decision_explanations",
    )
    op.drop_index(
        "ix_ai_decision_explanations_decision_id",
        table_name="ai_decision_explanations",
    )
    op.drop_index(
        "ix_ai_decision_explanations_decision_type",
        table_name="ai_decision_explanations",
    )
    op.drop_index(
        "ix_ai_decision_explanations_tenant_id",
        table_name="ai_decision_explanations",
    )
    op.drop_table("ai_decision_explanations")
