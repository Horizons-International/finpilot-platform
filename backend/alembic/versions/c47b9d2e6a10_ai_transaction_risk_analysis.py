# mypy: ignore-errors
"""Persist AI transaction-risk recommendations and transaction history."""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c47b9d2e6a10"
down_revision: Union[str, Sequence[str], None] = "ea91b4d7c602"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLAlchemy creates the enum from AuditEventType using the lowercase class
    # name by default. Keep this guarded for repositories with a renamed type.
    op.execute("""DO $$
        DECLARE enum_name text;
        BEGIN
            SELECT t.typname INTO enum_name
            FROM pg_type AS t
            WHERE t.typname IN ('auditeventtype', 'audit_event_type')
            LIMIT 1;
            IF enum_name IS NOT NULL THEN
                EXECUTE format(
                    'ALTER TYPE %I ADD VALUE IF NOT EXISTS %L',
                    enum_name,
                    'AI_TRANSACTION_RISK_ANALYZED'
                );
            END IF;
        END $$;""")

    op.create_table(
        "transaction_risk_analyses",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("compliance_case_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("risk_score", sa.Integer(), nullable=False),
        sa.Column("risk_level", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.String(length=5000), nullable=False),
        sa.Column("recommended_action", sa.String(length=3000), nullable=False),
        sa.Column(
            "risk_factors",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("provider_name", sa.String(length=100), nullable=False),
        sa.Column("model_name", sa.String(length=200), nullable=True),
        sa.Column(
            "context_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "transaction_summary",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "baseline_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "ai_response", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "risk_score >= 0 AND risk_score <= 100",
            name="ck_transaction_risk_analyses_score_range",
        ),
        sa.CheckConstraint(
            "risk_level IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')",
            name="ck_transaction_risk_analyses_level",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_transaction_risk_analyses_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name="fk_transaction_risk_analyses_customer_id_customers",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_transaction_risk_analyses_created_by_users",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["compliance_case_id"],
            ["compliance_cases.id"],
            name="fk_transaction_risk_analyses_compliance_case_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_transaction_risk_analyses"),
    )
    for name, column in (
        ("ix_transaction_risk_analyses_tenant_id", "tenant_id"),
        ("ix_transaction_risk_analyses_customer_id", "customer_id"),
        ("ix_transaction_risk_analyses_created_by", "created_by"),
        ("ix_transaction_risk_analyses_compliance_case_id", "compliance_case_id"),
        ("ix_transaction_risk_analyses_risk_level", "risk_level"),
        ("ix_transaction_risk_analyses_created_at", "created_at"),
    ):
        op.create_index(name, "transaction_risk_analyses", [column])
    op.create_index(
        "ix_transaction_risk_analyses_tenant_customer_created",
        "transaction_risk_analyses",
        ["tenant_id", "customer_id", "created_at"],
    )

    op.create_table(
        "transaction_risk_transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("analysis_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("transaction_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount", sa.Numeric(precision=20, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("destination_country", sa.String(length=100), nullable=False),
        sa.Column("transaction_type", sa.String(length=100), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_transaction_risk_transactions_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["analysis_id"],
            ["transaction_risk_analyses.id"],
            name="fk_transaction_risk_transactions_analysis_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name="fk_transaction_risk_transactions_customer_id_customers",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_transaction_risk_transactions"),
        sa.UniqueConstraint(
            "tenant_id",
            "transaction_id",
            name="uq_transaction_risk_transactions_tenant_txn",
        ),
    )
    for name, column in (
        ("ix_transaction_risk_transactions_tenant_id", "tenant_id"),
        ("ix_transaction_risk_transactions_analysis_id", "analysis_id"),
        ("ix_transaction_risk_transactions_customer_id", "customer_id"),
    ):
        op.create_index(name, "transaction_risk_transactions", [column])
    op.create_index(
        "ix_transaction_risk_transactions_customer_time",
        "transaction_risk_transactions",
        ["tenant_id", "customer_id", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_table("transaction_risk_transactions")
    op.drop_table("transaction_risk_analyses")
    # PostgreSQL enum values are intentionally not removed: that operation is
    # unsupported in-place and keeping an unused audit value is safe.
