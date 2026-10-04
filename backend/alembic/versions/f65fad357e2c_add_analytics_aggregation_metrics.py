# mypy: ignore-errors

"""add analytics aggregation metrics

Revision ID: f65fad357e2c
Revises: 8a3b570b7e25
Create Date: 2026-10-04 17:43:39.214821

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f65fad357e2c"
down_revision: Union[str, Sequence[str], None] = "8a3b570b7e25"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # analytics_customer_daily
    # -------------------------------------------------------------------------
    # Rename the existing snapshot/state columns to make their meaning clear.

    op.alter_column(
        "analytics_operations_daily",
        "task_sla_completed",
        new_column_name="ending_tasks_sla_completed_on_time",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )
    op.alter_column(
        "analytics_customer_daily",
        "verified_customers",
        new_column_name="ending_verified_customers",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    op.alter_column(
        "analytics_customer_daily",
        "total_customers",
        new_column_name="ending_total_customers",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    op.alter_column(
        "analytics_customer_daily",
        "pending_verification",
        new_column_name="ending_pending_verification_customers",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    op.alter_column(
        "analytics_customer_daily",
        "new_registrations",
        new_column_name="customers_registered_during_day",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    op.alter_column(
        "analytics_customer_daily",
        "rejected_customers",
        new_column_name="ending_rejected_customers",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    op.alter_column(
        "analytics_customer_daily",
        "suspended_customers",
        new_column_name="ending_suspended_customers",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    # New event metric.
    op.add_column(
        "analytics_customer_daily",
        sa.Column(
            "verification_approvals_during_day",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )

    # Remove the temporary server default after existing rows have been
    # backfilled with zero.
    op.alter_column(
        "analytics_customer_daily",
        "verification_approvals_during_day",
        server_default=None,
    )

    # -------------------------------------------------------------------------
    # analytics_compliance_daily
    # -------------------------------------------------------------------------
    op.alter_column(
        "analytics_compliance_daily",
        "total_alerts",
        new_column_name="ending_total_alerts",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    op.alter_column(
        "analytics_compliance_daily",
        "resolved_cases",
        new_column_name="ending_resolved_cases",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    op.alter_column(
        "analytics_compliance_daily",
        "medium_severity_alerts",
        new_column_name="ending_medium_severity_alerts",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    op.alter_column(
        "analytics_compliance_daily",
        "critical_risk_customers",
        new_column_name="ending_critical_risk_customers",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    op.alter_column(
        "analytics_compliance_daily",
        "high_risk_customers",
        new_column_name="ending_high_risk_customers",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    op.alter_column(
        "analytics_compliance_daily",
        "low_risk_customers",
        new_column_name="ending_low_risk_customers",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    op.alter_column(
        "analytics_compliance_daily",
        "high_severity_alerts",
        new_column_name="ending_high_severity_alerts",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    op.alter_column(
        "analytics_compliance_daily",
        "total_cases",
        new_column_name="ending_total_cases",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    op.alter_column(
        "analytics_compliance_daily",
        "critical_severity_alerts",
        new_column_name="ending_critical_severity_alerts",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    op.alter_column(
        "analytics_compliance_daily",
        "medium_risk_customers",
        new_column_name="ending_medium_risk_customers",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    op.alter_column(
        "analytics_compliance_daily",
        "low_severity_alerts",
        new_column_name="ending_low_severity_alerts",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    op.alter_column(
        "analytics_compliance_daily",
        "closed_cases",
        new_column_name="ending_closed_cases",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    op.alter_column(
        "analytics_compliance_daily",
        "open_cases",
        new_column_name="ending_open_cases",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    # New event metrics.
    op.add_column(
        "analytics_compliance_daily",
        sa.Column(
            "cases_created_during_day",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )

    op.add_column(
        "analytics_compliance_daily",
        sa.Column(
            "alerts_created_during_day",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )

    op.alter_column(
        "analytics_compliance_daily",
        "cases_created_during_day",
        server_default=None,
    )

    op.alter_column(
        "analytics_compliance_daily",
        "alerts_created_during_day",
        server_default=None,
    )

    # -------------------------------------------------------------------------
    # analytics_operations_daily
    # -------------------------------------------------------------------------
    op.alter_column(
        "analytics_operations_daily",
        "task_sla_approaching_deadline",
        new_column_name="ending_tasks_sla_approaching_deadline",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    op.alter_column(
        "analytics_operations_daily",
        "open_tasks",
        new_column_name="ending_open_tasks",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    op.alter_column(
        "analytics_operations_daily",
        "active_workflows",
        new_column_name="ending_active_workflows",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    op.alter_column(
        "analytics_operations_daily",
        "total_workflows",
        new_column_name="ending_total_workflows",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    op.alter_column(
        "analytics_operations_daily",
        "completed_tasks",
        new_column_name="ending_total_completed_tasks",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    op.alter_column(
        "analytics_operations_daily",
        "total_tasks",
        new_column_name="ending_total_tasks",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    op.alter_column(
        "analytics_operations_daily",
        "overdue_tasks",
        new_column_name="ending_overdue_tasks",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    op.alter_column(
        "analytics_operations_daily",
        "task_sla_breached",
        new_column_name="ending_tasks_sla_breached",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    op.alter_column(
        "analytics_operations_daily",
        "workflow_sla_breached",
        new_column_name="ending_workflows_sla_breached",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    op.alter_column(
        "analytics_operations_daily",
        "workflow_sla_completed",
        new_column_name="ending_workflows_sla_completed_on_time",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    op.alter_column(
        "analytics_operations_daily",
        "workflow_sla_within_sla",
        new_column_name="ending_workflows_sla_within_target",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    op.alter_column(
        "analytics_operations_daily",
        "failed_workflows",
        new_column_name="ending_total_failed_workflows",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    op.alter_column(
        "analytics_operations_daily",
        "task_sla_within_sla",
        new_column_name="ending_tasks_sla_within_target",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    op.alter_column(
        "analytics_operations_daily",
        "completed_workflows",
        new_column_name="ending_total_completed_workflows",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    op.alter_column(
        "analytics_operations_daily",
        "workflow_sla_approaching_deadline",
        new_column_name="ending_workflows_sla_approaching_deadline",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    # New task event metrics.
    op.add_column(
        "analytics_operations_daily",
        sa.Column(
            "tasks_created_during_day",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )

    op.add_column(
        "analytics_operations_daily",
        sa.Column(
            "tasks_completed_during_day",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )

    op.add_column(
        "analytics_operations_daily",
        sa.Column(
            "tasks_completed_within_sla_during_day",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )

    op.add_column(
        "analytics_operations_daily",
        sa.Column(
            "tasks_completed_breached_sla_during_day",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )

    # New workflow event metrics.
    op.add_column(
        "analytics_operations_daily",
        sa.Column(
            "workflows_started_during_day",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )

    op.add_column(
        "analytics_operations_daily",
        sa.Column(
            "workflows_completed_during_day",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )

    op.add_column(
        "analytics_operations_daily",
        sa.Column(
            "workflows_failed_during_day",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )

    op.add_column(
        "analytics_operations_daily",
        sa.Column(
            "workflows_completed_within_sla_during_day",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )

    op.add_column(
        "analytics_operations_daily",
        sa.Column(
            "workflows_completed_breached_sla_during_day",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )

    # Add the new task/workflow event metrics with an initial value of zero,
    # then remove the defaults so future inserts must provide the values.
    for column_name in (
        "tasks_created_during_day",
        "tasks_completed_during_day",
        "tasks_completed_within_sla_during_day",
        "tasks_completed_breached_sla_during_day",
        "workflows_started_during_day",
        "workflows_completed_during_day",
        "workflows_failed_during_day",
        "workflows_completed_within_sla_during_day",
        "workflows_completed_breached_sla_during_day",
    ):
        op.alter_column(
            "analytics_operations_daily",
            column_name,
            server_default=None,
        )

    # -------------------------------------------------------------------------
    # Monthly analytics tables
    # -------------------------------------------------------------------------
    op.create_table(
        "analytics_customer_monthly",
        sa.Column(
            "month_start",
            sa.Date(),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "ending_total_customers",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "customers_registered_during_month",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "verification_approvals_during_month",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "customer_growth",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "analytics_compliance_monthly",
        sa.Column(
            "month_start",
            sa.Date(),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "ending_total_cases",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "cases_created_during_month",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "ending_open_cases",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "ending_resolved_cases",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "ending_closed_cases",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "ending_total_alerts",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "alerts_created_during_month",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "ending_low_risk_customers",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "ending_medium_risk_customers",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "ending_high_risk_customers",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "ending_critical_risk_customers",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "analytics_operations_monthly",
        sa.Column(
            "month_start",
            sa.Date(),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "ending_total_tasks",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "tasks_created_during_month",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "tasks_completed_during_month",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "ending_open_tasks",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "ending_overdue_tasks",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "tasks_completed_within_sla_during_month",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "tasks_completed_breached_sla_during_month",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "ending_total_workflows",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "workflows_started_during_month",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "workflows_completed_during_month",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "workflows_failed_during_month",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "ending_active_workflows",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "workflows_completed_within_sla_during_month",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "workflows_completed_breached_sla_during_month",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    # -------------------------------------------------------------------------
    # Drop monthly analytics tables first.
    # -------------------------------------------------------------------------
    op.drop_table("analytics_operations_monthly")
    op.drop_table("analytics_compliance_monthly")
    op.drop_table("analytics_customer_monthly")

    # -------------------------------------------------------------------------
    # analytics_operations_daily
    # -------------------------------------------------------------------------
    for column_name in (
        "workflows_completed_breached_sla_during_day",
        "workflows_completed_within_sla_during_day",
        "workflows_failed_during_day",
        "workflows_completed_during_day",
        "workflows_started_during_day",
        "tasks_completed_breached_sla_during_day",
        "tasks_completed_within_sla_during_day",
        "tasks_completed_during_day",
        "tasks_created_during_day",
    ):
        op.drop_column(
            "analytics_operations_daily",
            column_name,
        )

    op.alter_column(
        "analytics_operations_daily",
        "ending_workflows_sla_approaching_deadline",
        new_column_name="workflow_sla_approaching_deadline",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    op.alter_column(
        "analytics_operations_daily",
        "ending_total_completed_workflows",
        new_column_name="completed_workflows",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    op.alter_column(
        "analytics_operations_daily",
        "ending_tasks_sla_within_target",
        new_column_name="task_sla_within_sla",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    op.alter_column(
        "analytics_operations_daily",
        "ending_total_failed_workflows",
        new_column_name="failed_workflows",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    op.alter_column(
        "analytics_operations_daily",
        "ending_workflows_sla_within_target",
        new_column_name="workflow_sla_within_sla",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    op.alter_column(
        "analytics_operations_daily",
        "ending_workflows_sla_completed_on_time",
        new_column_name="workflow_sla_completed",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    op.alter_column(
        "analytics_operations_daily",
        "ending_workflows_sla_breached",
        new_column_name="workflow_sla_breached",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    op.alter_column(
        "analytics_operations_daily",
        "ending_tasks_sla_breached",
        new_column_name="task_sla_breached",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    op.alter_column(
        "analytics_operations_daily",
        "ending_overdue_tasks",
        new_column_name="overdue_tasks",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    op.alter_column(
        "analytics_operations_daily",
        "ending_total_tasks",
        new_column_name="total_tasks",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    op.alter_column(
        "analytics_operations_daily",
        "ending_total_completed_tasks",
        new_column_name="completed_tasks",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    op.alter_column(
        "analytics_operations_daily",
        "ending_total_workflows",
        new_column_name="total_workflows",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    op.alter_column(
        "analytics_operations_daily",
        "ending_active_workflows",
        new_column_name="active_workflows",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    op.alter_column(
        "analytics_operations_daily",
        "ending_open_tasks",
        new_column_name="open_tasks",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    op.alter_column(
        "analytics_operations_daily",
        "ending_tasks_sla_approaching_deadline",
        new_column_name="task_sla_approaching_deadline",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    # -------------------------------------------------------------------------
    # analytics_compliance_daily
    # -------------------------------------------------------------------------
    op.drop_column(
        "analytics_compliance_daily",
        "alerts_created_during_day",
    )

    op.drop_column(
        "analytics_compliance_daily",
        "cases_created_during_day",
    )

    op.alter_column(
        "analytics_compliance_daily",
        "ending_open_cases",
        new_column_name="open_cases",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    op.alter_column(
        "analytics_compliance_daily",
        "ending_closed_cases",
        new_column_name="closed_cases",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    op.alter_column(
        "analytics_compliance_daily",
        "ending_low_severity_alerts",
        new_column_name="low_severity_alerts",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    op.alter_column(
        "analytics_compliance_daily",
        "ending_medium_risk_customers",
        new_column_name="medium_risk_customers",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    op.alter_column(
        "analytics_compliance_daily",
        "ending_critical_severity_alerts",
        new_column_name="critical_severity_alerts",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    op.alter_column(
        "analytics_compliance_daily",
        "ending_total_cases",
        new_column_name="total_cases",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    op.alter_column(
        "analytics_compliance_daily",
        "ending_high_severity_alerts",
        new_column_name="high_severity_alerts",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    op.alter_column(
        "analytics_compliance_daily",
        "ending_low_risk_customers",
        new_column_name="low_risk_customers",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    op.alter_column(
        "analytics_compliance_daily",
        "ending_high_risk_customers",
        new_column_name="high_risk_customers",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    op.alter_column(
        "analytics_compliance_daily",
        "ending_critical_risk_customers",
        new_column_name="critical_risk_customers",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    op.alter_column(
        "analytics_compliance_daily",
        "ending_medium_severity_alerts",
        new_column_name="medium_severity_alerts",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    op.alter_column(
        "analytics_compliance_daily",
        "ending_resolved_cases",
        new_column_name="resolved_cases",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    op.alter_column(
        "analytics_compliance_daily",
        "ending_total_alerts",
        new_column_name="total_alerts",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    # -------------------------------------------------------------------------
    # analytics_customer_daily
    # -------------------------------------------------------------------------
    op.drop_column(
        "analytics_customer_daily",
        "verification_approvals_during_day",
    )

    op.alter_column(
        "analytics_customer_daily",
        "ending_suspended_customers",
        new_column_name="suspended_customers",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    op.alter_column(
        "analytics_customer_daily",
        "ending_rejected_customers",
        new_column_name="rejected_customers",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    op.alter_column(
        "analytics_customer_daily",
        "customers_registered_during_day",
        new_column_name="new_registrations",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    op.alter_column(
        "analytics_customer_daily",
        "ending_pending_verification_customers",
        new_column_name="pending_verification",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    op.alter_column(
        "analytics_customer_daily",
        "ending_total_customers",
        new_column_name="total_customers",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    op.alter_column(
        "analytics_customer_daily",
        "ending_verified_customers",
        new_column_name="verified_customers",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    op.alter_column(
        "analytics_operations_daily",
        "ending_tasks_sla_completed_on_time",
        new_column_name="task_sla_completed",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )
