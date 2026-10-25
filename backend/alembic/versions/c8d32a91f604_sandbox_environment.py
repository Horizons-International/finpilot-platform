# mypy: ignore-errors
"""Create isolated sandbox accounts, synthetic customers, and mock events."""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c8d32a91f604"
down_revision: Union[str, Sequence[str], None] = "b7c34e8a6d21"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sandbox_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_name", sa.String(200), nullable=False),
        sa.Column("developer_name", sa.String(200), nullable=False),
        sa.Column("developer_email", sa.String(255), nullable=False),
        sa.Column("status", sa.String(20), server_default="ACTIVE", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'SUSPENDED')",
            name="ck_sandbox_accounts_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_sandbox_accounts_status_created",
        "sandbox_accounts",
        ["status", "created_at"],
    )

    op.create_table(
        "sandbox_organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sandbox_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["sandbox_account_id"], ["sandbox_accounts.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "sandbox_account_id", name="uq_sandbox_organizations_account"
        ),
        sa.UniqueConstraint("code"),
    )
    op.create_index(
        "ix_sandbox_organizations_sandbox_account_id",
        "sandbox_organizations",
        ["sandbox_account_id"],
    )

    op.create_table(
        "sandbox_users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sandbox_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("role", sa.String(40), server_default="DEVELOPER", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["sandbox_account_id"], ["sandbox_accounts.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "sandbox_account_id", "email", name="uq_sandbox_users_account_email"
        ),
        sa.CheckConstraint(
            "role IN ('DEVELOPER', 'OPERATOR', 'REVIEWER', 'AUDITOR')",
            name="ck_sandbox_users_role",
        ),
    )
    op.create_index(
        "ix_sandbox_users_sandbox_account_id",
        "sandbox_users",
        ["sandbox_account_id"],
    )

    op.create_table(
        "sandbox_api_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sandbox_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("key_prefix", sa.String(32), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column(
            "permissions",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("status", sa.String(20), server_default="ACTIVE", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'REVOKED')",
            name="ck_sandbox_api_keys_status",
        ),
        sa.ForeignKeyConstraint(
            ["sandbox_account_id"], ["sandbox_accounts.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key_hash", name="uq_sandbox_api_keys_hash"),
    )
    op.create_index(
        "ix_sandbox_api_keys_sandbox_account_id",
        "sandbox_api_keys",
        ["sandbox_account_id"],
    )
    op.create_index(
        "ix_sandbox_api_keys_account_status",
        "sandbox_api_keys",
        ["sandbox_account_id", "status"],
    )

    op.create_table(
        "sandbox_customers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sandbox_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("external_reference", sa.String(100), nullable=False),
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("last_name", sa.String(100), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("phone_number", sa.String(30), nullable=False),
        sa.Column("status", sa.String(32), server_default="NEW", nullable=False),
        sa.Column(
            "attributes",
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
        sa.ForeignKeyConstraint(
            ["sandbox_account_id"], ["sandbox_accounts.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "sandbox_account_id",
            "external_reference",
            name="uq_sandbox_customers_account_reference",
        ),
        sa.UniqueConstraint(
            "id", "sandbox_account_id", name="uq_sandbox_customers_id_account"
        ),
    )
    op.create_index(
        "ix_sandbox_customers_sandbox_account_id",
        "sandbox_customers",
        ["sandbox_account_id"],
    )
    op.create_index(
        "ix_sandbox_customers_account_created",
        "sandbox_customers",
        ["sandbox_account_id", "created_at"],
    )

    op.create_table(
        "sandbox_verifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sandbox_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scenario", sa.String(24), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column(
            "result",
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
            "scenario IN ('APPROVED', 'REJECTED', 'MANUAL_REVIEW')",
            name="ck_sandbox_verifications_scenario",
        ),
        sa.CheckConstraint(
            "status IN ('VERIFIED', 'REJECTED', 'REVIEW_REQUIRED')",
            name="ck_sandbox_verifications_status",
        ),
        sa.ForeignKeyConstraint(
            ["sandbox_account_id"], ["sandbox_accounts.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["customer_id", "sandbox_account_id"],
            ["sandbox_customers.id", "sandbox_customers.sandbox_account_id"],
            ondelete="CASCADE",
            name="fk_sandbox_verifications_customer_account",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_sandbox_verifications_sandbox_account_id",
        "sandbox_verifications",
        ["sandbox_account_id"],
    )
    op.create_index(
        "ix_sandbox_verifications_customer_id",
        "sandbox_verifications",
        ["customer_id"],
    )
    op.create_index(
        "ix_sandbox_verifications_account_created",
        "sandbox_verifications",
        ["sandbox_account_id", "created_at"],
    )

    op.create_table(
        "sandbox_webhooks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sandbox_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("endpoint_url", sa.String(2048), nullable=True),
        sa.Column(
            "event_types",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("status", sa.String(20), server_default="ACTIVE", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["sandbox_account_id"], ["sandbox_accounts.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "id", "sandbox_account_id", name="uq_sandbox_webhooks_id_account"
        ),
    )
    op.create_index(
        "ix_sandbox_webhooks_sandbox_account_id",
        "sandbox_webhooks",
        ["sandbox_account_id"],
    )
    op.create_index(
        "ix_sandbox_webhooks_account_created",
        "sandbox_webhooks",
        ["sandbox_account_id", "created_at"],
    )

    op.create_table(
        "sandbox_webhook_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sandbox_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("webhook_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column(
            "delivery_status",
            sa.String(32),
            server_default="SIMULATED_NOT_SENT",
            nullable=False,
        ),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "delivery_status IN ('SIMULATED_NOT_SENT')",
            name="ck_sandbox_webhook_events_delivery_status",
        ),
        sa.ForeignKeyConstraint(
            ["sandbox_account_id"], ["sandbox_accounts.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["webhook_id", "sandbox_account_id"],
            ["sandbox_webhooks.id", "sandbox_webhooks.sandbox_account_id"],
            ondelete="CASCADE",
            name="fk_sandbox_webhook_events_webhook_account",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_sandbox_webhook_events_sandbox_account_id",
        "sandbox_webhook_events",
        ["sandbox_account_id"],
    )
    op.create_index(
        "ix_sandbox_webhook_events_webhook_id",
        "sandbox_webhook_events",
        ["webhook_id"],
    )
    op.create_index(
        "ix_sandbox_webhook_events_webhook_created",
        "sandbox_webhook_events",
        ["webhook_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("sandbox_webhook_events")
    op.drop_table("sandbox_webhooks")
    op.drop_table("sandbox_verifications")
    op.drop_table("sandbox_customers")
    op.drop_table("sandbox_api_keys")
    op.drop_table("sandbox_users")
    op.drop_table("sandbox_organizations")
    op.drop_table("sandbox_accounts")
