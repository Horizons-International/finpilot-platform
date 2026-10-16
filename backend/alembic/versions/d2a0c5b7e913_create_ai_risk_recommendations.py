# mypy: ignore-errors
"""Create tenant-scoped AI risk recommendation history.

Revision ID: d2a0c5b7e913
Revises: c1a4e6f8d2b9
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d2a0c5b7e913"
down_revision: Union[str, Sequence[str], None] = "c1a4e6f8d2b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_risk_recommendations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("compliance_case_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("risk_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("risk_level", sa.String(length=16), nullable=False),
        sa.Column("recommendation", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("suggested_action", sa.Text(), nullable=False),
        sa.Column("required_review_type", sa.String(length=64), nullable=False),
        sa.Column(
            "risk_factors",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("confidence", sa.Float(), server_default="0", nullable=False),
        sa.Column(
            "input_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("provider_name", sa.String(length=100), nullable=False),
        sa.Column("model_name", sa.String(length=200), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "risk_score >= 0 AND risk_score <= 100",
            name="ck_ai_risk_recommendations_score_range",
        ),
        sa.CheckConstraint(
            "risk_level IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')",
            name="ck_ai_risk_recommendations_risk_level",
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_ai_risk_recommendations_confidence_range",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_ai_risk_recommendations_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name="fk_ai_risk_recommendations_customer_id_customers",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["compliance_case_id"],
            ["compliance_cases.id"],
            name="fk_ai_risk_recommendations_compliance_case_id_cases",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_ai_risk_recommendations_created_by_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_risk_recommendations_tenant_id",
        "ai_risk_recommendations",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_risk_recommendations_customer_id",
        "ai_risk_recommendations",
        ["customer_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_risk_recommendations_compliance_case_id",
        "ai_risk_recommendations",
        ["compliance_case_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_risk_recommendations_created_by",
        "ai_risk_recommendations",
        ["created_by"],
        unique=False,
    )
    op.create_index(
        "ix_ai_risk_recommendations_created_at",
        "ai_risk_recommendations",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_ai_risk_recommendations_tenant_customer_created",
        "ai_risk_recommendations",
        ["tenant_id", "customer_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_ai_risk_recommendations_tenant_case_created",
        "ai_risk_recommendations",
        ["tenant_id", "compliance_case_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_risk_recommendations_tenant_case_created",
        table_name="ai_risk_recommendations",
    )
    op.drop_index(
        "ix_ai_risk_recommendations_tenant_customer_created",
        table_name="ai_risk_recommendations",
    )
    op.drop_index(
        "ix_ai_risk_recommendations_created_at",
        table_name="ai_risk_recommendations",
    )
    op.drop_index(
        "ix_ai_risk_recommendations_created_by",
        table_name="ai_risk_recommendations",
    )
    op.drop_index(
        "ix_ai_risk_recommendations_compliance_case_id",
        table_name="ai_risk_recommendations",
    )
    op.drop_index(
        "ix_ai_risk_recommendations_customer_id",
        table_name="ai_risk_recommendations",
    )
    op.drop_index(
        "ix_ai_risk_recommendations_tenant_id",
        table_name="ai_risk_recommendations",
    )
    op.drop_table("ai_risk_recommendations")
