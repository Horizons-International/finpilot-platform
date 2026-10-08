# mypy: ignore-errors

"""add user invitations

Revision ID: 9f5aa30e2059
Revises: 32b33c437946
Create Date: 2026-10-08 23:38:03.685408

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9f5aa30e2059"
down_revision: Union[str, Sequence[str], None] = "32b33c437946"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_invitations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "email",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "first_name",
            sa.String(length=100),
            nullable=False,
        ),
        sa.Column(
            "last_name",
            sa.String(length=100),
            nullable=False,
        ),
        sa.Column(
            "role",
            sa.String(length=50),
            nullable=False,
        ),
        sa.Column(
            "department",
            sa.String(length=100),
            nullable=True,
        ),
        sa.Column(
            "token_hash",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "invited_by",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "accepted_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "revoked_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_user_invitations_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["invited_by"],
            ["users.id"],
            name="fk_user_invitations_invited_by_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name="pk_user_invitations",
        ),
        sa.UniqueConstraint(
            "token_hash",
            name="uq_user_invitations_token_hash",
        ),
    )

    op.create_index(
        "ix_user_invitations_tenant_id",
        "user_invitations",
        ["tenant_id"],
        unique=False,
    )

    op.create_index(
        "ix_user_invitations_email",
        "user_invitations",
        ["email"],
        unique=False,
    )

    op.create_index(
        "ix_user_invitations_token_hash",
        "user_invitations",
        ["token_hash"],
        unique=False,
    )

    op.create_index(
        "ix_user_invitations_expires_at",
        "user_invitations",
        ["expires_at"],
        unique=False,
    )

    op.create_index(
        "ix_user_invitations_invited_by",
        "user_invitations",
        ["invited_by"],
        unique=False,
    )

    op.execute("ALTER TYPE auditeventtype ADD VALUE IF NOT EXISTS 'USER_INVITED'")
    op.execute(
        "ALTER TYPE auditeventtype ADD VALUE IF NOT EXISTS 'USER_INVITATION_ACCEPTED'"
    )
    op.execute("ALTER TYPE auditeventtype ADD VALUE IF NOT EXISTS 'USER_ROLE_CHANGED'")


def downgrade() -> None:
    op.drop_index(
        "ix_user_invitations_invited_by",
        table_name="user_invitations",
    )

    op.drop_index(
        "ix_user_invitations_expires_at",
        table_name="user_invitations",
    )

    op.drop_index(
        "ix_user_invitations_token_hash",
        table_name="user_invitations",
    )

    op.drop_index(
        "ix_user_invitations_email",
        table_name="user_invitations",
    )

    op.drop_index(
        "ix_user_invitations_tenant_id",
        table_name="user_invitations",
    )

    op.drop_table(
        "user_invitations",
    )
