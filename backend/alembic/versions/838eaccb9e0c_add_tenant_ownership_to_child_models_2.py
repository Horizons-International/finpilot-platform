# mypy: ignore-errors

"""Add tenant ownership to child models 2.

Revision ID: 838eaccb9e0c
Revises: 193f1517c0df
Create Date: 2026-10-11 04:19:41.566036
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "838eaccb9e0c"
down_revision: Union[str, Sequence[str], None] = "193f1517c0df"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _assert_no_null_tenant_ids(table_name: str) -> None:
    bind = op.get_bind()
    null_count = bind.execute(
        sa.text(f"SELECT COUNT(*) FROM {table_name} WHERE tenant_id IS NULL")
    ).scalar_one()

    if null_count:
        raise RuntimeError(
            f"Cannot apply tenant ownership to {table_name}: "
            f"{null_count} row(s) could not be assigned to a tenant."
        )


def _finish_tenant_column(table_name: str) -> None:
    op.alter_column(
        table_name,
        "tenant_id",
        existing_type=sa.UUID(),
        nullable=False,
    )
    op.create_index(
        f"ix_{table_name}_tenant_id",
        table_name,
        ["tenant_id"],
        unique=False,
    )
    op.create_foreign_key(
        f"fk_{table_name}_tenant_id_tenants",
        table_name,
        "tenants",
        ["tenant_id"],
        ["id"],
        ondelete="CASCADE",
    )


def _drop_tenant_column(table_name: str) -> None:
    op.drop_constraint(
        f"fk_{table_name}_tenant_id_tenants",
        table_name,
        type_="foreignkey",
    )
    op.drop_index(f"ix_{table_name}_tenant_id", table_name=table_name)
    op.drop_column(table_name, "tenant_id")


def _backfill_metric_definition_tenant_ids() -> None:
    bind = op.get_bind()

    cross_tenant_definition = bind.execute(
        sa.text(  # fmt: skip
            """
            SELECT metric_definition_id
            FROM metric_results
            WHERE tenant_id IS NOT NULL
            GROUP BY metric_definition_id
            HAVING COUNT(DISTINCT tenant_id) > 1
            LIMIT 1
            """
        )
    ).first()

    if cross_tenant_definition is not None:
        raise RuntimeError(
            "Cannot assign tenant ownership to metric_definitions: "
            "at least one definition has results for multiple tenants. "
            "Resolve those definitions explicitly before applying this migration."
        )

    bind.execute(
        sa.text(  # fmt: skip
            """
            UPDATE metric_definitions AS definition
            SET tenant_id = result_tenants.tenant_id
            FROM (
                SELECT
                    metric_definition_id,
                    MIN(tenant_id::text)::uuid AS tenant_id
                FROM metric_results
                WHERE tenant_id IS NOT NULL
                GROUP BY metric_definition_id
                HAVING COUNT(DISTINCT tenant_id) = 1
            ) AS result_tenants
            WHERE result_tenants.metric_definition_id = definition.id
              AND definition.tenant_id IS NULL
            """
        )
    )

    null_count = bind.execute(
        sa.text("SELECT COUNT(*) FROM metric_definitions WHERE tenant_id IS NULL")
    ).scalar_one()

    if not null_count:
        return

    tenant_ids = list(
        bind.execute(sa.text("SELECT id FROM tenants ORDER BY id LIMIT 2")).scalars()
    )

    if len(tenant_ids) != 1:
        raise RuntimeError(
            "Cannot determine tenant ownership for metric definitions without "
            "tenant-specific results. Assign those definitions explicitly, "
            "or ensure the database contains exactly one tenant before retrying."
        )

    bind.execute(
        sa.text(
            "UPDATE metric_definitions SET tenant_id = :tenant_id "
            "WHERE tenant_id IS NULL"
        ),
        {"tenant_id": tenant_ids[0]},
    )


def upgrade() -> None:
    op.add_column(
        "ai_prompts",
        sa.Column("tenant_id", sa.UUID(), nullable=True),
    )
    op.execute(
        sa.text(  # fmt: skip
            """
            UPDATE ai_prompts AS prompt
            SET tenant_id = creator.tenant_id
            FROM users AS creator
            WHERE prompt.created_by = creator.id
              AND prompt.tenant_id IS NULL
            """
        )
    )
    _assert_no_null_tenant_ids("ai_prompts")
    _finish_tenant_column("ai_prompts")

    op.add_column(
        "ai_prompt_assignments",
        sa.Column("tenant_id", sa.UUID(), nullable=True),
    )
    op.execute(
        sa.text(  # fmt: skip
            """
            UPDATE ai_prompt_assignments AS assignment
            SET tenant_id = prompt.tenant_id
            FROM ai_prompts AS prompt
            WHERE assignment.prompt_id = prompt.id
              AND assignment.tenant_id IS NULL
            """
        )
    )
    _assert_no_null_tenant_ids("ai_prompt_assignments")
    _finish_tenant_column("ai_prompt_assignments")

    op.add_column(
        "metric_definitions",
        sa.Column("tenant_id", sa.UUID(), nullable=True),
    )
    _backfill_metric_definition_tenant_ids()
    _assert_no_null_tenant_ids("metric_definitions")
    _finish_tenant_column("metric_definitions")

    op.add_column(
        "workflow_steps",
        sa.Column("tenant_id", sa.UUID(), nullable=True),
    )
    op.execute(
        sa.text(  # fmt: skip
            """
            UPDATE workflow_steps AS step
            SET tenant_id = workflow.tenant_id
            FROM workflows AS workflow
            WHERE step.workflow_id = workflow.id
              AND step.tenant_id IS NULL
            """
        )
    )
    _assert_no_null_tenant_ids("workflow_steps")
    _finish_tenant_column("workflow_steps")

    op.add_column(
        "knowledge_document_chunks", sa.Column("tenant_id", sa.UUID(), nullable=False)
    )
    op.create_index(
        op.f("ix_knowledge_document_chunks_tenant_id"),
        "knowledge_document_chunks",
        ["tenant_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_knowledge_document_chunks_tenant_id",
        "knowledge_document_chunks",
        "tenants",
        ["tenant_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.add_column("notifications", sa.Column("tenant_id", sa.UUID(), nullable=False))
    op.create_index(
        op.f("ix_notifications_tenant_id"), "notifications", ["tenant_id"], unique=False
    )
    op.create_foreign_key(
        "fk_notifications_tenant_id",
        "notifications",
        "tenants",
        ["tenant_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        op.f("ix_customer_status_history_customer_id"),
        "customer_status_history",
        ["customer_id"],
        unique=False,
    )


def downgrade() -> None:
    _drop_tenant_column("workflow_steps")
    _drop_tenant_column("metric_definitions")
    _drop_tenant_column("ai_prompt_assignments")
    _drop_tenant_column("ai_prompts")
    op.drop_constraint(
        "fk_knowledge_document_chunks_tenant_id",
        "knowledge_document_chunks",
        type_="foreignkey",
    )
    op.drop_index(
        op.f("ix_knowledge_document_chunks_tenant_id"),
        table_name="knowledge_document_chunks",
    )
    op.drop_column("knowledge_document_chunks", "tenant_id")
    op.drop_constraint(
        "fk_notifications_tenant_id", "notifications", type_="foreignkey"
    )
    op.drop_index(op.f("ix_notifications_tenant_id"), table_name="notifications")
    op.drop_column("notifications", "tenant_id")
    op.drop_index(
        op.f("ix_customer_status_history_customer_id"),
        table_name="customer_status_history",
    )
