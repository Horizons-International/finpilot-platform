# mypy: ignore_errors

"""add tenant isolation to business entities

Revision ID: 683f1f0daf98
Revises: 9f5aa30e2059
Create Date: 2026-10-09 16:47:25.676450

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "683f1f0daf98"
down_revision: Union[str, Sequence[str], None] = "9f5aa30e2059"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_single_tenant_id(bind):
    """
    Return the tenant ID only when the database contains exactly one tenant.

    This is a safe fallback for legacy records without enough information
    to infer ownership. It must never assign ambiguous rows arbitrarily.
    """
    tenant_ids = list(bind.execute(sa.text("SELECT id FROM tenants LIMIT 2")).scalars())

    if len(tenant_ids) != 1:
        raise RuntimeError(
            "Cannot determine tenant ownership for existing records. "
            "The database does not contain exactly one tenant. "
            "Assign the unresolved records to their correct tenants "
            "before retrying this migration."
        )

    return tenant_ids[0]


def _backfill_remaining_rows(table_name):
    """
    Fill any remaining NULL tenant IDs only when the database has
    exactly one tenant.

    table_name must be a hard-coded table name supplied by this migration.
    """
    bind = op.get_bind()

    remaining = bind.execute(
        sa.text(f"SELECT COUNT(*) FROM {table_name} WHERE tenant_id IS NULL")
    ).scalar_one()

    if remaining == 0:
        return

    tenant_id = _get_single_tenant_id(bind)

    bind.execute(
        sa.text(
            f"UPDATE {table_name} SET tenant_id = :tenant_id WHERE tenant_id IS NULL"
        ),
        {"tenant_id": tenant_id},
    )


def _assert_no_null_tenant_ids(table_name):
    """Fail rather than silently assigning incomplete tenant ownership."""
    bind = op.get_bind()

    remaining = bind.execute(
        sa.text(f"SELECT COUNT(*) FROM {table_name} WHERE tenant_id IS NULL")
    ).scalar_one()

    if remaining:
        raise RuntimeError(
            f"Migration cannot continue: {table_name} "
            f"contains {remaining} records without tenant ownership."
        )


def _backfill_task_tenant_ids():
    """
    Resolve task ownership from the most reliable existing relationships:

    1. Workflow execution.
    2. Workflow step execution.
    3. Assigned user.
    4. A single-tenant fallback for any remaining legacy rows.
    """
    bind = op.get_bind()

    # Tasks associated with a workflow execution inherit the workflow tenant.
    bind.execute(
        sa.text(  # fmt: skip
            """
            UPDATE tasks AS t
            SET tenant_id = w.tenant_id
            FROM workflow_executions AS we
            JOIN workflows AS w
              ON w.id = we.workflow_id
            WHERE t.workflow_execution_id = we.id
              AND t.tenant_id IS NULL
            """
        )
    )

    # Some tasks reference a workflow step execution instead.
    bind.execute(
        sa.text(  # fmt: skip
            """
            UPDATE tasks AS t
            SET tenant_id = w.tenant_id
            FROM workflow_step_executions AS wse
            JOIN workflow_executions AS we
              ON we.id = wse.workflow_execution_id
            JOIN workflows AS w
              ON w.id = we.workflow_id
            WHERE t.workflow_step_execution_id = wse.id
              AND t.tenant_id IS NULL
            """
        )
    )

    # Standalone tasks may only have an assignee.
    bind.execute(
        sa.text(  # fmt: skip
            """
            UPDATE tasks AS t
            SET tenant_id = u.tenant_id
            FROM users AS u
            WHERE t.assigned_to = u.id
              AND t.tenant_id IS NULL
            """
        )
    )

    _backfill_remaining_rows("tasks")
    _assert_no_null_tenant_ids("tasks")


def _backfill_knowledge_document_tenant_ids():
    """
    Fill missing knowledge-document ownership from the uploader.

    The supplied Alembic output shows that tenant_id already exists on
    knowledge_documents; therefore this migration does not add that column.
    """
    bind = op.get_bind()

    bind.execute(
        sa.text(  # fmt: skip
            """
            UPDATE knowledge_documents AS kd
            SET tenant_id = u.tenant_id
            FROM users AS u
            WHERE kd.uploaded_by = u.id
              AND kd.tenant_id IS NULL
            """
        )
    )

    _backfill_remaining_rows("knowledge_documents")
    _assert_no_null_tenant_ids("knowledge_documents")


def _assert_no_cross_tenant_knowledge_duplicates():
    """
    Verify that reverting to globally unique knowledge-document names
    would not violate the old constraints.
    """
    bind = op.get_bind()

    duplicate_version = bind.execute(
        sa.text(  # fmt: skip
            """
            SELECT name, version
            FROM knowledge_documents
            GROUP BY name, version
            HAVING COUNT(*) > 1
            LIMIT 1
            """
        )
    ).first()

    if duplicate_version is not None:
        raise RuntimeError(
            "Cannot downgrade: knowledge documents in different tenants "
            "share the same name and version."
        )

    duplicate_active_name = bind.execute(
        sa.text(  # fmt: skip
            """
            SELECT name
            FROM knowledge_documents
            WHERE status::text = 'ACTIVE'
            GROUP BY name
            HAVING COUNT(*) > 1
            LIMIT 1
            """
        )
    ).first()

    if duplicate_active_name is not None:
        raise RuntimeError(
            "Cannot downgrade: multiple tenants have an active "
            "knowledge document with the same name."
        )


# ---------------------------------------------------------------------------
# Upgrade
# ---------------------------------------------------------------------------


def upgrade():
    # 1. Add task ownership as nullable so legacy data can be backfilled.
    op.add_column(
        "tasks",
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )

    # 2. Backfill task ownership before enforcing NOT NULL or adding its FK.
    _backfill_task_tenant_ids()

    # 3. Enforce task ownership at the database level.
    op.alter_column(
        "tasks",
        "tenant_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )

    op.create_foreign_key(
        "fk_tasks_tenant_id",
        "tasks",
        "tenants",
        ["tenant_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.create_index(
        "ix_tasks_tenant_id",
        "tasks",
        ["tenant_id"],
        unique=False,
    )

    # 4. Backfill missing knowledge-document ownership if necessary.

    op.add_column(
        "knowledge_documents",
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )

    _backfill_knowledge_document_tenant_ids()

    op.alter_column(
        "knowledge_documents",
        "tenant_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )

    # 5. Add the missing tenant index and foreign key.
    op.create_foreign_key(
        "fk_knowledge_documents_tenant_id",
        "knowledge_documents",
        "tenants",
        ["tenant_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.create_index(
        "ix_knowledge_documents_tenant_id",
        "knowledge_documents",
        ["tenant_id"],
        unique=False,
    )

    # 6. Replace the global active-document-name index with a
    #    tenant-scoped partial unique index.
    op.drop_index(
        "uq_knowledge_documents_active_name",
        table_name="knowledge_documents",
    )

    op.create_index(
        "uq_knowledge_documents_active_name",
        "knowledge_documents",
        ["tenant_id", "name"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )

    # 7. Replace global name/version uniqueness with tenant-scoped
    #    name/version uniqueness.
    op.drop_constraint(
        "uq_knowledge_documents_name_version",
        "knowledge_documents",
        type_="unique",
    )

    op.create_unique_constraint(
        "uq_knowledge_documents_tenant_name_version",
        "knowledge_documents",
        ["tenant_id", "name", "version"],
    )

    op.add_column("compliance_cases", sa.Column("tenant_id", sa.UUID(), nullable=False))
    op.create_index(
        op.f("ix_compliance_cases_tenant_id"),
        "compliance_cases",
        ["tenant_id"],
        unique=False,
    )
    op.create_foreign_key(
        "compliance_case_tenant_id",
        "compliance_cases",
        "tenants",
        ["tenant_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.add_column(
        "customer_documents", sa.Column("tenant_id", sa.UUID(), nullable=False)
    )
    op.create_index(
        op.f("ix_customer_documents_tenant_id"),
        "customer_documents",
        ["tenant_id"],
        unique=False,
    )
    op.create_foreign_key(
        "customer_document_tenant_id",
        "customer_documents",
        "tenants",
        ["tenant_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.add_column("files", sa.Column("tenant_id", sa.UUID(), nullable=False))
    op.create_index(op.f("ix_files_tenant_id"), "files", ["tenant_id"], unique=False)
    op.create_foreign_key(
        "file_tenant_id", "files", "tenants", ["tenant_id"], ["id"], ondelete="CASCADE"
    )
    op.add_column(
        "identity_verification_cases", sa.Column("tenant_id", sa.UUID(), nullable=False)
    )
    op.create_index(
        op.f("ix_identity_verification_cases_tenant_id"),
        "identity_verification_cases",
        ["tenant_id"],
        unique=False,
    )
    op.create_foreign_key(
        "verification_case_tenant_id",
        "identity_verification_cases",
        "tenants",
        ["tenant_id"],
        ["id"],
        ondelete="CASCADE",
    )


# ---------------------------------------------------------------------------
# Downgrade
# ---------------------------------------------------------------------------


def downgrade():
    # Check first: restoring global uniqueness must not fail partway through
    # the downgrade if different tenants now have duplicate names.
    _assert_no_cross_tenant_knowledge_duplicates()

    # 1. Restore the old globally unique knowledge-document name/version.
    op.drop_constraint(
        "uq_knowledge_documents_tenant_name_version",
        "knowledge_documents",
        type_="unique",
    )

    op.create_unique_constraint(
        "uq_knowledge_documents_name_version",
        "knowledge_documents",
        ["name", "version"],
    )

    # 2. Restore the old global active-document-name index.
    op.drop_index(
        "uq_knowledge_documents_active_name",
        table_name="knowledge_documents",
    )

    op.create_index(
        "uq_knowledge_documents_active_name",
        "knowledge_documents",
        ["name"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )

    # 3. Remove the tenant index and FK added by this migration.
    op.drop_index(
        "ix_knowledge_documents_tenant_id",
        table_name="knowledge_documents",
    )

    op.drop_constraint(
        "fk_knowledge_documents_tenant_id",
        "knowledge_documents",
        type_="foreignkey",
    )

    # Do not drop knowledge_documents.tenant_id: this migration did not
    # add that column according to the supplied Alembic diff.

    # 4. Remove task tenant ownership, reverting the column added by
    #    this migration.
    op.drop_index(
        "ix_tasks_tenant_id",
        table_name="tasks",
    )

    op.drop_constraint(
        "fk_tasks_tenant_id",
        "tasks",
        type_="foreignkey",
    )

    op.drop_column(
        "tasks",
        "tenant_id",
    )

    op.drop_column(
        "knowledge_documents",
        "tenant_id",
    )

    op.drop_constraint(
        "verification_case_tenant_id", "identity_verification_cases", type_="foreignkey"
    )
    op.drop_index(
        op.f("ix_identity_verification_cases_tenant_id"),
        table_name="identity_verification_cases",
    )
    op.drop_column("identity_verification_cases", "tenant_id")
    op.drop_constraint("file_tenant_id", "files", type_="foreignkey")
    op.drop_index(op.f("ix_files_tenant_id"), table_name="files")
    op.drop_column("files", "tenant_id")
    op.drop_constraint(
        "customer_document_tenant_id", "customer_documents", type_="foreignkey"
    )
    op.drop_index(
        op.f("ix_customer_documents_tenant_id"), table_name="customer_documents"
    )
    op.drop_column("customer_documents", "tenant_id")
    op.drop_constraint(
        "compliance_case_tenant_id", "compliance_cases", type_="foreignkey"
    )
    op.drop_index(op.f("ix_compliance_cases_tenant_id"), table_name="compliance_cases")
    op.drop_column("compliance_cases", "tenant_id")
