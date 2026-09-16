# mypy: ignore-errors

"""create ai prompt management

Revision ID: 8f05c0a05b48
Revises: d3ad739be233
Create Date: 2026-09-16 12:35:53.726115

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8f05c0a05b48"
down_revision: Union[str, Sequence[str], None] = "d3ad739be233"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_prompts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "name",
            sa.String(length=100),
            nullable=False,
        ),
        sa.Column(
            "purpose",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "prompt_text",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "version",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "ACTIVE", "INACTIVE", name="ai_prompt_status", create_constraint=True
            ),
            nullable=False,
            server_default="INACTIVE",
        ),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "name",
            "version",
            name="uq_ai_prompts_name_version",
        ),
    )

    op.create_index(
        "ix_ai_prompts_name",
        "ai_prompts",
        ["name"],
    )

    op.create_index(
        "ix_ai_prompts_status",
        "ai_prompts",
        ["status"],
    )

    # Only one active version can exist for a prompt name.
    op.create_index(
        "uq_ai_prompts_active_name",
        "ai_prompts",
        ["name"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )

    op.create_table(
        "ai_prompt_assignments",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "ai_function",
            sa.Enum(
                "DOCUMENT_EXTRACTION",
                "COMPLIANCE_REVIEW",
                "RISK_ANALYSIS",
                "CUSTOMER_SUPPORT",
                name="ai_function",
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "prompt_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["prompt_id"],
            ["ai_prompts.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "ai_function",
            name="uq_ai_prompt_assignments_function",
        ),
    )

    op.create_index(
        "ix_ai_prompt_assignments_ai_function",
        "ai_prompt_assignments",
        ["ai_function"],
    )

    op.execute("ALTER TYPE auditeventtype ADD VALUE IF NOT EXISTS 'AI_PROMPT_CREATED'")
    op.execute(
        "ALTER TYPE auditeventtype ADD VALUE IF NOT EXISTS 'AI_PROMPT_VERSION_CREATED'"
    )
    op.execute(
        "ALTER TYPE auditeventtype ADD VALUE IF NOT EXISTS 'AI_PROMPT_ACTIVATED'"
    )
    op.execute(
        "ALTER TYPE auditeventtype ADD VALUE IF NOT EXISTS 'AI_PROMPT_DEACTIVATED'"
    )
    op.execute("ALTER TYPE auditeventtype ADD VALUE IF NOT EXISTS 'AI_PROMPT_ASSIGNED'")


def downgrade() -> None:
    op.drop_index(
        "ix_ai_prompt_assignments_ai_function",
        table_name="ai_prompt_assignments",
    )

    op.drop_table("ai_prompt_assignments")

    op.drop_index(
        "uq_ai_prompts_active_name",
        table_name="ai_prompts",
    )

    op.drop_index(
        "ix_ai_prompts_status",
        table_name="ai_prompts",
    )

    op.drop_index(
        "ix_ai_prompts_name",
        table_name="ai_prompts",
    )

    op.drop_table("ai_prompts")
