# mypy: ignore-errors

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "193f1517c0df"
down_revision: Union[str, Sequence[str], None] = "daae3c52a401"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TENANT_TABLES = (
    ("ai_interactions", False),
    ("ai_usage_logs", False),
    ("aml_rules", False),
    ("audit_logs", True),
    ("communication_logs", False),
    ("compliance_case_history", False),
    ("customer_addresses", False),
    ("customer_audit_logs", False),
    ("customer_contacts", False),
    ("customer_risk_assessment_history", False),
    ("customer_risk_profiles", False),
    ("customer_status_history", False),
    ("document_extraction_review_logs", False),
    ("investigation_notes", False),
    ("metric_results", False),
    ("notification_deliveries", False),
    ("risk_predictions", False),
    ("risk_scoring_rules", False),
    ("task_assignment_rules", False),
    ("task_comments", False),
    ("task_status_history", False),
    ("transaction_monitoring_results", False),
    ("verification_case_assignment_history", False),
    ("verification_reviews", False),
    ("workflow_audit_logs", False),
    ("workflow_executions", False),
    ("workflow_step_executions", False),
)


def _add_tenant_id(table_name: str, nullable: bool) -> None:
    op.add_column(
        table_name,
        sa.Column("tenant_id", sa.UUID(), nullable=nullable),
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


def _drop_tenant_id(table_name: str) -> None:
    op.drop_constraint(
        f"fk_{table_name}_tenant_id_tenants",
        table_name,
        type_="foreignkey",
    )
    op.drop_index(
        f"ix_{table_name}_tenant_id",
        table_name=table_name,
    )
    op.drop_column(table_name, "tenant_id")


def upgrade() -> None:
    for table_name, nullable in TENANT_TABLES:
        _add_tenant_id(table_name, nullable)

    op.drop_constraint(
        "workflow_audit_logs_workflow_id_fkey",
        "workflow_audit_logs",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_workflow_audit_logs_workflow_id",
        table_name="workflow_audit_logs",
    )
    op.drop_index(
        "ix_workflow_audit_logs_workflow_created",
        table_name="workflow_audit_logs",
    )
    op.alter_column(
        "workflow_audit_logs",
        "workflow_id",
        new_column_name="workflow_execution_id",
        existing_type=sa.UUID(),
        existing_nullable=False,
    )
    op.create_index(
        "ix_workflow_audit_logs_workflow_created",
        "workflow_audit_logs",
        ["workflow_execution_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_workflow_audit_logs_workflow_execution_id",
        "workflow_audit_logs",
        ["workflow_execution_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_workflow_audit_logs_execution_id_workflow_executions",
        "workflow_audit_logs",
        "workflow_executions",
        ["workflow_execution_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_workflow_audit_logs_execution_id_workflow_executions",
        "workflow_audit_logs",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_workflow_audit_logs_workflow_execution_id",
        table_name="workflow_audit_logs",
    )
    op.drop_index(
        "ix_workflow_audit_logs_workflow_created",
        table_name="workflow_audit_logs",
    )
    op.alter_column(
        "workflow_audit_logs",
        "workflow_execution_id",
        new_column_name="workflow_id",
        existing_type=sa.UUID(),
        existing_nullable=False,
    )
    op.create_index(
        "ix_workflow_audit_logs_workflow_created",
        "workflow_audit_logs",
        ["workflow_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_workflow_audit_logs_workflow_id",
        "workflow_audit_logs",
        ["workflow_id"],
        unique=False,
    )
    op.create_foreign_key(
        "workflow_audit_logs_workflow_id_fkey",
        "workflow_audit_logs",
        "workflow_executions",
        ["workflow_id"],
        ["id"],
        ondelete="CASCADE",
    )

    for table_name, _ in reversed(TENANT_TABLES):
        _drop_tenant_id(table_name)
