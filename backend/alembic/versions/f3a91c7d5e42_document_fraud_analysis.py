# mypy: ignore-errors
"""Persist tenant-scoped document authenticity screening results."""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "f3a91c7d5e42"
down_revision: Union[str, Sequence[str], None] = "e8b41c7d2a90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "document_fraud_analyses",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "status", sa.String(length=16), server_default="PENDING", nullable=False
        ),
        sa.Column("risk_score", sa.Numeric(5, 2), server_default="0", nullable=False),
        sa.Column(
            "risk_level", sa.String(length=16), server_default="LOW", nullable=False
        ),
        sa.Column(
            "needs_manual_review",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "result",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("provider_name", sa.String(length=100), nullable=True),
        sa.Column("model_name", sa.String(length=200), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('PENDING', 'COMPLETED', 'FAILED')",
            name="ck_document_fraud_analyses_status",
        ),
        sa.CheckConstraint(
            "risk_score >= 0 AND risk_score <= 100",
            name="ck_document_fraud_analyses_score_range",
        ),
        sa.CheckConstraint(
            "risk_level IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')",
            name="ck_document_fraud_analyses_risk_level",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_document_fraud_analyses_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["customer_documents.id"],
            name="fk_document_fraud_analyses_document_id_customer_documents",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name="fk_document_fraud_analyses_customer_id_customers",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by"],
            ["users.id"],
            name="fk_document_fraud_analyses_requested_by_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_document_fraud_analyses"),
    )
    op.create_index(
        "ix_document_fraud_analyses_tenant_id",
        "document_fraud_analyses",
        ["tenant_id"],
    )
    op.create_index(
        "ix_document_fraud_analyses_document_id",
        "document_fraud_analyses",
        ["document_id"],
    )
    op.create_index(
        "ix_document_fraud_analyses_customer_id",
        "document_fraud_analyses",
        ["customer_id"],
    )
    op.create_index(
        "ix_document_fraud_analyses_requested_by",
        "document_fraud_analyses",
        ["requested_by"],
    )
    op.create_index(
        "ix_document_fraud_analyses_created_at",
        "document_fraud_analyses",
        ["created_at"],
    )
    op.create_index(
        "ix_document_fraud_analyses_tenant_document_created",
        "document_fraud_analyses",
        ["tenant_id", "document_id", "created_at"],
    )
    op.create_index(
        "ix_document_fraud_analyses_tenant_customer_created",
        "document_fraud_analyses",
        ["tenant_id", "customer_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_document_fraud_analyses_tenant_customer_created",
        table_name="document_fraud_analyses",
    )
    op.drop_index(
        "ix_document_fraud_analyses_tenant_document_created",
        table_name="document_fraud_analyses",
    )
    op.drop_index(
        "ix_document_fraud_analyses_created_at",
        table_name="document_fraud_analyses",
    )
    op.drop_index(
        "ix_document_fraud_analyses_requested_by",
        table_name="document_fraud_analyses",
    )
    op.drop_index(
        "ix_document_fraud_analyses_customer_id",
        table_name="document_fraud_analyses",
    )
    op.drop_index(
        "ix_document_fraud_analyses_document_id",
        table_name="document_fraud_analyses",
    )
    op.drop_index(
        "ix_document_fraud_analyses_tenant_id",
        table_name="document_fraud_analyses",
    )
    op.drop_table("document_fraud_analyses")
