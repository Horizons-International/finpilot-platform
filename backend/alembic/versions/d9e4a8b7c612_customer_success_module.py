# mypy: ignore-errors
"""Add customer-success lifecycle profiles, usage, support and history."""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d9e4a8b7c612"
down_revision: Union[str, Sequence[str], None] = "c8d32a91f604"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "customer_success_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "account_status",
            sa.String(length=20),
            server_default="TRIAL",
            nullable=False,
        ),
        sa.Column(
            "implementation_stage",
            sa.String(length=32),
            server_default="NOT_STARTED",
            nullable=False,
        ),
        sa.Column("assigned_manager_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("success_plan", sa.Text(), nullable=True),
        sa.Column("last_contacted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("health_score", sa.Integer(), server_default="100", nullable=False),
        sa.Column(
            "health_band",
            sa.String(length=24),
            server_default="HEALTHY",
            nullable=False,
        ),
        sa.Column(
            "health_score_updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
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
            "account_status IN ('TRIAL', 'ACTIVE', 'AT_RISK', 'PAUSED', 'CHURNED')",
            name="ck_customer_success_profile_account_status",
        ),
        sa.CheckConstraint(
            "implementation_stage IN ('NOT_STARTED', 'CONFIGURATION', 'INTEGRATION', "
            "'TESTING', 'READY_FOR_PRODUCTION', 'LIVE')",
            name="ck_customer_success_profile_implementation_stage",
        ),
        sa.CheckConstraint(
            "health_score >= 0 AND health_score <= 100",
            name="ck_customer_success_profile_health_score",
        ),
        sa.CheckConstraint(
            "health_band IN ('HEALTHY', 'NEEDS_ATTENTION', 'AT_RISK')",
            name="ck_customer_success_profile_health_band",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["customer_tenant_id"], ["tenants.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["assigned_manager_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "customer_tenant_id",
            name="uq_customer_success_profile_customer",
        ),
        sa.UniqueConstraint(
            "id", "tenant_id", name="uq_customer_success_profile_id_tenant"
        ),
    )
    op.create_index(
        "ix_customer_success_profiles_tenant_id",
        "customer_success_profiles",
        ["tenant_id"],
    )
    op.create_index(
        "ix_customer_success_profiles_customer_tenant_id",
        "customer_success_profiles",
        ["customer_tenant_id"],
    )
    op.create_index(
        "ix_customer_success_profiles_assigned_manager_id",
        "customer_success_profiles",
        ["assigned_manager_id"],
    )
    op.create_index(
        "ix_customer_success_profile_tenant_health",
        "customer_success_profiles",
        ["tenant_id", "health_band"],
    )
    op.create_index(
        "ix_customer_success_profile_tenant_status",
        "customer_success_profiles",
        ["tenant_id", "account_status"],
    )

    op.create_table(
        "customer_success_usage_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("active_users", sa.Integer(), nullable=False),
        sa.Column("licensed_users", sa.Integer(), nullable=False),
        sa.Column("api_calls", sa.Integer(), nullable=False),
        sa.Column("api_call_limit", sa.Integer(), nullable=True),
        sa.Column("active_features", sa.Integer(), nullable=False),
        sa.Column("available_features", sa.Integer(), nullable=False),
        sa.Column(
            "source", sa.String(length=32), server_default="MANUAL", nullable=False
        ),
        sa.Column("recorded_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "period_end >= period_start", name="ck_customer_success_usage_period_dates"
        ),
        sa.CheckConstraint(
            (
                "active_users >= 0 AND licensed_users >= 0 "
                "AND active_users <= licensed_users"
            ),
            name="ck_customer_success_usage_user_counts",
        ),
        sa.CheckConstraint(
            "api_calls >= 0 AND (api_call_limit IS NULL OR api_call_limit >= 0)",
            name="ck_customer_success_usage_api_counts",
        ),
        sa.CheckConstraint(
            "active_features >= 0 AND available_features >= 0 "
            "AND active_features <= available_features",
            name="ck_customer_success_usage_feature_counts",
        ),
        sa.ForeignKeyConstraint(
            ["profile_id", "tenant_id"],
            ["customer_success_profiles.id", "customer_success_profiles.tenant_id"],
            name="fk_customer_success_usage_profile_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["recorded_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "profile_id", "period_start", name="uq_customer_success_usage_period"
        ),
    )
    op.create_index(
        "ix_customer_success_usage_snapshots_tenant_id",
        "customer_success_usage_snapshots",
        ["tenant_id"],
    )
    op.create_index(
        "ix_customer_success_usage_profile_period",
        "customer_success_usage_snapshots",
        ["profile_id", "period_start"],
    )

    op.create_table(
        "customer_success_support_interactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subject", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "category", sa.String(length=20), server_default="QUESTION", nullable=False
        ),
        sa.Column(
            "severity", sa.String(length=12), server_default="MEDIUM", nullable=False
        ),
        sa.Column(
            "status", sa.String(length=24), server_default="OPEN", nullable=False
        ),
        sa.Column("assigned_to", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
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
            (
                "category IN ('INCIDENT', 'QUESTION', 'REQUEST', 'BILLING', "
                "'INTEGRATION', 'TRAINING', 'OTHER')"
            ),
            name="ck_customer_success_support_category",
        ),
        sa.CheckConstraint(
            "severity IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')",
            name="ck_customer_success_support_severity",
        ),
        sa.CheckConstraint(
            (
                "status IN ('OPEN', 'IN_PROGRESS', 'WAITING_CUSTOMER', "
                "'RESOLVED', 'CLOSED')"
            ),
            name="ck_customer_success_support_status",
        ),
        sa.ForeignKeyConstraint(
            ["profile_id", "tenant_id"],
            ["customer_success_profiles.id", "customer_success_profiles.tenant_id"],
            name="fk_customer_success_support_profile_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["assigned_to"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_customer_success_support_interactions_tenant_id",
        "customer_success_support_interactions",
        ["tenant_id"],
    )
    op.create_index(
        "ix_customer_success_support_profile_status",
        "customer_success_support_interactions",
        ["profile_id", "status"],
    )
    op.create_index(
        "ix_customer_success_support_tenant_created",
        "customer_success_support_interactions",
        ["tenant_id", "created_at"],
    )

    op.create_table(
        "customer_success_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column(
            "event_data",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["profile_id", "tenant_id"],
            ["customer_success_profiles.id", "customer_success_profiles.tenant_id"],
            name="fk_customer_success_history_profile_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_customer_success_history_tenant_id",
        "customer_success_history",
        ["tenant_id"],
    )
    op.create_index(
        "ix_customer_success_history_profile_created",
        "customer_success_history",
        ["profile_id", "created_at"],
    )
    op.create_index(
        "ix_customer_success_history_created_at",
        "customer_success_history",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_table("customer_success_history")
    op.drop_table("customer_success_support_interactions")
    op.drop_table("customer_success_usage_snapshots")
    op.drop_table("customer_success_profiles")
