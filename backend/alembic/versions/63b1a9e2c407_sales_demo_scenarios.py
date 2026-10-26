# mypy: ignore-errors
"""Add isolated synthetic sales-demo scenario records."""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "63b1a9e2c407"
down_revision: Union[str, Sequence[str], None] = "f31a9c0e4d72"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sandbox_demo_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sandbox_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("record_type", sa.String(length=40), nullable=False),
        sa.Column("scenario_key", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column(
            "data",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "record_type IN ('COMPLIANCE_CASE', 'AML_ALERT', 'AI_RISK_RECOMMENDATION', "
            "'INVESTIGATION_SUMMARY', 'DASHBOARD', 'REPORT', 'WORKFLOW')",
            name="ck_sandbox_demo_records_type",
        ),
        sa.ForeignKeyConstraint(
            ["sandbox_account_id"], ["sandbox_accounts.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["customer_id", "sandbox_account_id"],
            ["sandbox_customers.id", "sandbox_customers.sandbox_account_id"],
            ondelete="CASCADE",
            name="fk_sandbox_demo_records_customer_account",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "sandbox_account_id",
            "scenario_key",
            name="uq_sandbox_demo_records_account_scenario",
        ),
    )
    op.create_index(
        "ix_sandbox_demo_records_sandbox_account_id",
        "sandbox_demo_records",
        ["sandbox_account_id"],
    )
    op.create_index(
        "ix_sandbox_demo_records_customer_id",
        "sandbox_demo_records",
        ["customer_id"],
    )
    op.create_index(
        "ix_sandbox_demo_records_account_type_created",
        "sandbox_demo_records",
        ["sandbox_account_id", "record_type", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_sandbox_demo_records_account_type_created",
        table_name="sandbox_demo_records",
    )
    op.drop_index(
        "ix_sandbox_demo_records_customer_id",
        table_name="sandbox_demo_records",
    )
    op.drop_index(
        "ix_sandbox_demo_records_sandbox_account_id",
        table_name="sandbox_demo_records",
    )
    op.drop_table("sandbox_demo_records")
