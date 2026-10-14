# mypy: ignore-errors
"""Add tenant subscriptions and monthly usage metering."""

import json
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "ea91b4d7c602"
down_revision: Union[str, Sequence[str], None] = "d6e5a7f1c922"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    subscription_status = postgresql.ENUM(
        "trial",
        "active",
        "past_due",
        "suspended",
        "cancelled",
        "expired",
        name="subscription_status",
        create_type=False,
    )
    subscription_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_name", sa.String(length=32), nullable=False),
        sa.Column(
            "status",
            subscription_status,
            server_default="active",
            nullable=False,
        ),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column(
            "usage_limits",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "features",
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
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_subscriptions_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_subscriptions"),
    )
    op.create_index("ix_subscriptions_tenant_id", "subscriptions", ["tenant_id"])
    op.create_index("ix_subscriptions_plan_name", "subscriptions", ["plan_name"])
    op.create_index("ix_subscriptions_status", "subscriptions", ["status"])
    op.create_index(
        "uq_subscriptions_current_tenant",
        "subscriptions",
        ["tenant_id"],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('trial'::subscription_status, 'active'::subscription_status)"
        ),
    )

    op.create_table(
        "subscription_usage_counters",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("metric", sa.String(length=32), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("used", sa.Integer(), server_default="0", nullable=False),
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
        sa.CheckConstraint("used >= 0", name="ck_subscription_usage_used_nonnegative"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_subscription_usage_counters_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_subscription_usage_counters"),
        sa.UniqueConstraint(
            "tenant_id",
            "metric",
            "period_start",
            name="uq_subscription_usage_tenant_metric_period",
        ),
    )
    op.create_index(
        "ix_subscription_usage_counters_tenant_id",
        "subscription_usage_counters",
        ["tenant_id"],
    )
    op.create_index(
        "ix_subscription_usage_tenant_period",
        "subscription_usage_counters",
        ["tenant_id", "period_start"],
    )

    # Existing organizations receive a bounded Starter subscription so enabling
    # metering does not strand already onboarded tenants after deployment.
    starter_limits = {
        "max_users": 100,
        "api_calls": 50000,
        "verification_checks": 1000,
        "ai_requests": 500,
        "transactions": 1000,
        "storage_bytes": 1073741824,
    }
    starter_features = {"advanced_reporting": False, "dedicated_integrations": False}
    bind = op.get_bind()
    tenant_rows = bind.execute(sa.text("SELECT id FROM tenants")).fetchall()
    for row in tenant_rows:
        bind.execute(
            sa.text(
                "INSERT INTO subscriptions "
                "(id, tenant_id, plan_name, status, "
                "start_date, end_date, usage_limits, features) "
                "VALUES (:id, :tenant_id, 'starter', 'active', "
                "(NOW() AT TIME ZONE 'UTC')::date, "
                "(NOW() AT TIME ZONE 'UTC')::date + 365, "
                "CAST(:usage_limits AS jsonb), CAST(:features AS jsonb))"
            ),
            {
                "id": str(uuid.uuid4()),
                "tenant_id": str(row[0]),
                "usage_limits": json.dumps(starter_limits),
                "features": json.dumps(starter_features),
            },
        )


def downgrade() -> None:
    op.drop_index(
        "ix_subscription_usage_tenant_period", table_name="subscription_usage_counters"
    )
    op.drop_index(
        "ix_subscription_usage_counters_tenant_id",
        table_name="subscription_usage_counters",
    )
    op.drop_table("subscription_usage_counters")
    op.drop_index("uq_subscriptions_current_tenant", table_name="subscriptions")
    op.drop_index("ix_subscriptions_status", table_name="subscriptions")
    op.drop_index("ix_subscriptions_plan_name", table_name="subscriptions")
    op.drop_index("ix_subscriptions_tenant_id", table_name="subscriptions")
    op.drop_table("subscriptions")
    postgresql.ENUM(
        "trial",
        "active",
        "past_due",
        "suspended",
        "cancelled",
        "expired",
        name="subscription_status",
    ).drop(op.get_bind(), checkfirst=True)
