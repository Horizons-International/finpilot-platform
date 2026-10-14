# mypy: ignore-errors

"""Create tenant-scoped integration configurations and health metadata.

Revision ID: a7d2f91c4e61
Revises: 838eaccb9e0c
Create Date: 2026-10-14 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a7d2f91c4e61"
down_revision: Union[str, Sequence[str], None] = "6f8a4c1d9b20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INTEGRATION_TYPES = (
    "IDENTITY_VERIFICATION",
    "BANKING",
    "PAYMENT",
    "NOTIFICATION",
    "DATA",
)
_INTEGRATION_STATUSES = ("UNKNOWN", "HEALTHY", "DEGRADED", "ERROR")
_AUDIT_EVENTS = (
    "INTEGRATION_CREATED",
    "INTEGRATION_UPDATED",
    "INTEGRATION_ENABLED",
    "INTEGRATION_DISABLED",
    "INTEGRATION_CONNECTION_CHECKED",
    "INTEGRATION_CONNECTION_FAILED",
)


def upgrade() -> None:
    for event_name in _AUDIT_EVENTS:
        op.execute(f"ALTER TYPE auditeventtype ADD VALUE IF NOT EXISTS '{event_name}'")

    integration_type = postgresql.ENUM(
        *_INTEGRATION_TYPES,
        name="integration_type",
        create_type=False,
    )
    integration_status = postgresql.ENUM(
        *_INTEGRATION_STATUSES,
        name="integration_status",
        create_type=False,
    )
    integration_type.create(op.get_bind(), checkfirst=True)
    integration_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "integrations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_name", sa.String(length=100), nullable=False),
        sa.Column("integration_type", integration_type, nullable=False),
        sa.Column(
            "configuration",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "is_enabled",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "status",
            integration_status,
            server_default="UNKNOWN",
            nullable=False,
        ),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=1000), nullable=True),
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
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_integrations_tenant_id", "integrations", ["tenant_id"])
    op.create_index("ix_integrations_provider_name", "integrations", ["provider_name"])
    op.create_index(
        "ix_integrations_integration_type", "integrations", ["integration_type"]
    )
    op.create_index("ix_integrations_is_enabled", "integrations", ["is_enabled"])
    op.create_index("ix_integrations_status", "integrations", ["status"])
    op.create_index("ix_integrations_created_at", "integrations", ["created_at"])
    op.create_index(
        "ix_integrations_tenant_type",
        "integrations",
        ["tenant_id", "integration_type"],
    )
    op.create_index(
        "ix_integrations_tenant_enabled",
        "integrations",
        ["tenant_id", "is_enabled"],
    )


def downgrade() -> None:
    op.drop_index("ix_integrations_tenant_enabled", table_name="integrations")
    op.drop_index("ix_integrations_tenant_type", table_name="integrations")
    op.drop_index("ix_integrations_created_at", table_name="integrations")
    op.drop_index("ix_integrations_status", table_name="integrations")
    op.drop_index("ix_integrations_is_enabled", table_name="integrations")
    op.drop_index("ix_integrations_integration_type", table_name="integrations")
    op.drop_index("ix_integrations_provider_name", table_name="integrations")
    op.drop_index("ix_integrations_tenant_id", table_name="integrations")
    op.drop_table("integrations")
    postgresql.ENUM(name="integration_status").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="integration_type").drop(op.get_bind(), checkfirst=True)
    # PostgreSQL enum values cannot be removed safely as part of this downgrade.
    # The INTEGRATION_* audit event variants therefore remain in auditeventtype.
