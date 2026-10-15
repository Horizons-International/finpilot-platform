# mypy: ignore-errors
"""Store tenant-scoped transaction activity and detected anomaly events."""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "af52c8d1e740"
down_revision: Union[str, Sequence[str], None] = "c47b9d2e6a10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "transaction_anomaly_activity",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("transaction_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount", sa.Numeric(20, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("destination_country", sa.String(length=100), nullable=True),
        sa.Column("beneficiary_id", sa.String(length=255), nullable=True),
        sa.Column(
            "transaction_type",
            sa.String(length=100),
            server_default="TRANSFER",
            nullable=False,
        ),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "amount > 0",
            name="ck_transaction_anomaly_activity_amount_positive",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_transaction_anomaly_activity_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name="fk_transaction_anomaly_activity_customer_id_customers",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_transaction_anomaly_activity"),
        sa.UniqueConstraint(
            "tenant_id",
            "transaction_id",
            name="uq_transaction_anomaly_activity_tenant_transaction",
        ),
    )
    op.create_index(
        "ix_transaction_anomaly_activity_tenant_id",
        "transaction_anomaly_activity",
        ["tenant_id"],
    )
    op.create_index(
        "ix_transaction_anomaly_activity_customer_id",
        "transaction_anomaly_activity",
        ["customer_id"],
    )
    op.create_index(
        "ix_transaction_anomaly_activity_occurred_at",
        "transaction_anomaly_activity",
        ["occurred_at"],
    )
    op.create_index(
        "ix_transaction_anomaly_activity_tenant_customer_time",
        "transaction_anomaly_activity",
        ["tenant_id", "customer_id", "occurred_at"],
    )

    op.create_table(
        "transaction_anomalies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("transaction_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("anomaly_type", sa.String(length=64), nullable=False),
        sa.Column("risk_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("risk_level", sa.String(length=16), nullable=False),
        sa.Column("summary", sa.String(length=1000), nullable=False),
        sa.Column(
            "details",
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
            "risk_score >= 0 AND risk_score <= 100",
            name="ck_transaction_anomalies_risk_score_range",
        ),
        sa.CheckConstraint(
            "risk_level IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')",
            name="ck_transaction_anomalies_risk_level",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_transaction_anomalies_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name="fk_transaction_anomalies_customer_id_customers",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_transaction_anomalies"),
    )
    op.create_index(
        "ix_transaction_anomalies_tenant_id", "transaction_anomalies", ["tenant_id"]
    )
    op.create_index(
        "ix_transaction_anomalies_customer_id", "transaction_anomalies", ["customer_id"]
    )
    op.create_index(
        "ix_transaction_anomalies_transaction_id",
        "transaction_anomalies",
        ["transaction_id"],
    )
    op.create_index(
        "ix_transaction_anomalies_anomaly_type",
        "transaction_anomalies",
        ["anomaly_type"],
    )
    op.create_index(
        "ix_transaction_anomalies_risk_level", "transaction_anomalies", ["risk_level"]
    )
    op.create_index(
        "ix_transaction_anomalies_created_at", "transaction_anomalies", ["created_at"]
    )
    op.create_index(
        "ix_transaction_anomalies_tenant_customer_created",
        "transaction_anomalies",
        ["tenant_id", "customer_id", "created_at"],
    )
    op.create_index(
        "ix_transaction_anomalies_tenant_transaction",
        "transaction_anomalies",
        ["tenant_id", "transaction_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_transaction_anomalies_tenant_transaction",
        table_name="transaction_anomalies",
    )
    op.drop_index(
        "ix_transaction_anomalies_tenant_customer_created",
        table_name="transaction_anomalies",
    )
    op.drop_index(
        "ix_transaction_anomalies_created_at", table_name="transaction_anomalies"
    )
    op.drop_index(
        "ix_transaction_anomalies_risk_level", table_name="transaction_anomalies"
    )
    op.drop_index(
        "ix_transaction_anomalies_anomaly_type", table_name="transaction_anomalies"
    )
    op.drop_index(
        "ix_transaction_anomalies_transaction_id", table_name="transaction_anomalies"
    )
    op.drop_index(
        "ix_transaction_anomalies_customer_id", table_name="transaction_anomalies"
    )
    op.drop_index(
        "ix_transaction_anomalies_tenant_id", table_name="transaction_anomalies"
    )
    op.drop_table("transaction_anomalies")
    op.drop_index(
        "ix_transaction_anomaly_activity_tenant_customer_time",
        table_name="transaction_anomaly_activity",
    )
    op.drop_index(
        "ix_transaction_anomaly_activity_occurred_at",
        table_name="transaction_anomaly_activity",
    )
    op.drop_index(
        "ix_transaction_anomaly_activity_customer_id",
        table_name="transaction_anomaly_activity",
    )
    op.drop_index(
        "ix_transaction_anomaly_activity_tenant_id",
        table_name="transaction_anomaly_activity",
    )
    op.drop_table("transaction_anomaly_activity")
