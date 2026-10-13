# mypy: ignore-errors

"""Create tenant-scoped API key management and usage tracking."""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "6f8a4c1d9b20"
down_revision: Union[str, Sequence[str], None] = "838eaccb9e0c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # AuditEventType uses PostgreSQL's auditeventtype enum in this repository.
    op.execute("ALTER TYPE auditeventtype ADD VALUE IF NOT EXISTS 'API_KEY_CREATED'")
    op.execute("ALTER TYPE auditeventtype ADD VALUE IF NOT EXISTS 'API_KEY_REVOKED'")

    api_key_status = postgresql.ENUM(
        "ACTIVE",
        "REVOKED",
        name="api_key_status",
        create_type=False,
    )
    api_key_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "api_keys",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "permissions",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "status",
            api_key_status,
            server_default="ACTIVE",
            nullable=False,
        ),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key_hash", name="uq_api_keys_key_hash"),
    )
    op.create_index("ix_api_keys_tenant_id", "api_keys", ["tenant_id"], unique=False)
    op.create_index("ix_api_keys_status", "api_keys", ["status"], unique=False)
    op.create_index("ix_api_keys_created_by", "api_keys", ["created_by"], unique=False)
    op.create_index("ix_api_keys_created_at", "api_keys", ["created_at"], unique=False)

    op.create_table(
        "api_key_usages",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("api_key_id", sa.UUID(), nullable=False),
        sa.Column("method", sa.String(length=10), nullable=False),
        sa.Column("path", sa.String(length=500), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["api_key_id"], ["api_keys.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_api_key_usages_tenant_id",
        "api_key_usages",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_api_key_usages_api_key_id",
        "api_key_usages",
        ["api_key_id"],
        unique=False,
    )
    op.create_index(
        "ix_api_key_usages_created_at",
        "api_key_usages",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_api_key_usages_key_created",
        "api_key_usages",
        ["api_key_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_api_key_usages_key_created", table_name="api_key_usages")
    op.drop_index("ix_api_key_usages_created_at", table_name="api_key_usages")
    op.drop_index("ix_api_key_usages_api_key_id", table_name="api_key_usages")
    op.drop_index("ix_api_key_usages_tenant_id", table_name="api_key_usages")
    op.drop_table("api_key_usages")

    op.drop_index("ix_api_keys_created_at", table_name="api_keys")
    op.drop_index("ix_api_keys_created_by", table_name="api_keys")
    op.drop_index("ix_api_keys_status", table_name="api_keys")
    op.drop_index("ix_api_keys_tenant_id", table_name="api_keys")
    op.drop_table("api_keys")
    op.execute("DROP TYPE api_key_status")
    # PostgreSQL cannot remove individual enum labels safely in a migration.
    # API_KEY_CREATED and API_KEY_REVOKED therefore remain unused on downgrade.
