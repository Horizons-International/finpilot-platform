# mypy: ignore-errors

"""Make AI prompt names and function assignments tenant-local.

Revision ID: f4d9c23a8b61
Revises: 8a5761ee8c1e
Create Date: 2026-11-17 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "f4d9c23a8b61"
down_revision: Union[str, Sequence[str], None] = "8a5761ee8c1e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Replace global AI prompt uniqueness with tenant-scoped constraints."""
    op.drop_constraint(
        "uq_ai_prompts_name_version",
        "ai_prompts",
        type_="unique",
    )
    op.drop_index(
        "uq_ai_prompts_active_name",
        table_name="ai_prompts",
    )
    op.create_unique_constraint(
        "uq_ai_prompts_tenant_name_version",
        "ai_prompts",
        ["tenant_id", "name", "version"],
    )
    op.create_index(
        "uq_ai_prompts_active_tenant_name",
        "ai_prompts",
        ["tenant_id", "name"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )

    op.drop_constraint(
        "uq_ai_prompt_assignments_function",
        "ai_prompt_assignments",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_ai_prompt_assignments_tenant_function",
        "ai_prompt_assignments",
        ["tenant_id", "ai_function"],
    )
    op.drop_index(
        op.f("ix_ai_prompt_assignments_ai_function"), table_name="ai_prompt_assignments"
    )
    op.create_index(
        op.f("ix_ai_prompt_assignments_ai_function"),
        "ai_prompt_assignments",
        ["ai_function"],
        unique=False,
    )


def _assert_global_uniqueness_can_be_restored() -> None:
    """Prevent a downgrade that would fail after tenants reuse global keys."""
    bind = op.get_bind()
    checks = (
        (
            "prompt name/version pairs",
            """
            SELECT name
            FROM ai_prompts
            GROUP BY name, version
            HAVING COUNT(*) > 1
            LIMIT 1
            """,
        ),
        (
            "active prompt names",
            """
            SELECT name
            FROM ai_prompts
            WHERE status = 'ACTIVE'
            GROUP BY name
            HAVING COUNT(*) > 1
            LIMIT 1
            """,
        ),
        (
            "AI function assignments",
            """
            SELECT ai_function
            FROM ai_prompt_assignments
            GROUP BY ai_function
            HAVING COUNT(*) > 1
            LIMIT 1
            """,
        ),
    )
    for description, statement in checks:
        if bind.execute(sa.text(statement)).first() is not None:
            raise RuntimeError(
                "Cannot downgrade AI prompt tenant-scoped uniqueness because "
                f"multiple tenants currently share {description}. Resolve those "
                "records before retrying the downgrade."
            )


def downgrade() -> None:
    """Restore the prior global constraints when existing data permits it."""
    _assert_global_uniqueness_can_be_restored()

    op.drop_constraint(
        "uq_ai_prompt_assignments_tenant_function",
        "ai_prompt_assignments",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_ai_prompt_assignments_function",
        "ai_prompt_assignments",
        ["ai_function"],
    )

    op.drop_index(
        "uq_ai_prompts_active_tenant_name",
        table_name="ai_prompts",
    )
    op.drop_constraint(
        "uq_ai_prompts_tenant_name_version",
        "ai_prompts",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_ai_prompts_name_version",
        "ai_prompts",
        ["name", "version"],
    )
    op.create_index(
        "uq_ai_prompts_active_name",
        "ai_prompts",
        ["name"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )
    op.drop_index(
        op.f("ix_ai_prompt_assignments_ai_function"), table_name="ai_prompt_assignments"
    )
    op.create_index(
        op.f("ix_ai_prompt_assignments_ai_function"),
        "ai_prompt_assignments",
        ["ai_function"],
        unique=True,
    )
