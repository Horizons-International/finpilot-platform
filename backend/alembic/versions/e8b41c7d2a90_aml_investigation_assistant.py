# mypy: ignore-errors
"""Persist structured AI-assisted AML investigation analyses and their sources."""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "e8b41c7d2a90"
down_revision: Union[str, Sequence[str], None] = "af52c8d1e740"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "aml_investigation_analyses",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("compliance_case_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column(
            "status", sa.String(length=16), server_default="PENDING", nullable=False
        ),
        sa.Column(
            "source_context",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "sources",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_aml_investigation_analyses_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_aml_investigation_analyses_created_by_users",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name="fk_aml_investigation_analyses_customer_id_customers",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["compliance_case_id"],
            ["compliance_cases.id"],
            name="fk_aml_investigation_analyses_compliance_case_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_aml_investigation_analyses"),
        sa.CheckConstraint(
            "status IN ('PENDING', 'COMPLETED', 'FAILED')",
            name="ck_aml_investigation_analyses_status",
        ),
    )
    op.create_index(
        "ix_aml_investigation_analyses_tenant_id",
        "aml_investigation_analyses",
        ["tenant_id"],
    )
    op.create_index(
        "ix_aml_investigation_analyses_created_by",
        "aml_investigation_analyses",
        ["created_by"],
    )
    op.create_index(
        "ix_aml_investigation_analyses_customer_id",
        "aml_investigation_analyses",
        ["customer_id"],
    )
    op.create_index(
        "ix_aml_investigation_analyses_compliance_case_id",
        "aml_investigation_analyses",
        ["compliance_case_id"],
    )
    op.create_index(
        "ix_aml_investigation_analyses_created_at",
        "aml_investigation_analyses",
        ["created_at"],
    )
    op.create_index(
        "ix_aml_investigation_analyses_tenant_customer_created",
        "aml_investigation_analyses",
        ["tenant_id", "customer_id", "created_at"],
    )
    op.create_index(
        "ix_aml_investigation_analyses_tenant_case_created",
        "aml_investigation_analyses",
        ["tenant_id", "compliance_case_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_aml_investigation_analyses_tenant_case_created",
        table_name="aml_investigation_analyses",
    )
    op.drop_index(
        "ix_aml_investigation_analyses_tenant_customer_created",
        table_name="aml_investigation_analyses",
    )
    op.drop_index(
        "ix_aml_investigation_analyses_created_at",
        table_name="aml_investigation_analyses",
    )
    op.drop_index(
        "ix_aml_investigation_analyses_compliance_case_id",
        table_name="aml_investigation_analyses",
    )
    op.drop_index(
        "ix_aml_investigation_analyses_customer_id",
        table_name="aml_investigation_analyses",
    )
    op.drop_index(
        "ix_aml_investigation_analyses_created_by",
        table_name="aml_investigation_analyses",
    )
    op.drop_index(
        "ix_aml_investigation_analyses_tenant_id",
        table_name="aml_investigation_analyses",
    )
    op.drop_table("aml_investigation_analyses")
