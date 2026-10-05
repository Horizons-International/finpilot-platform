# mypy: ignore-errors

"""add configurable metrics engine

Revision ID: 6f05d1794b4d
Revises: f65fad357e2c
Create Date: 2026-10-05 17:33:31.048994

"""

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6f05d1794b4d"
down_revision: Union[str, Sequence[str], None] = "f65fad357e2c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    metric_category = postgresql.ENUM(
        "CUSTOMER",
        "COMPLIANCE",
        "OPERATIONS",
        name="metric_category",
    )

    metric_status = postgresql.ENUM(
        "ACTIVE",
        "INACTIVE",
        name="metric_status",
    )

    metric_value_type = postgresql.ENUM(
        "PERCENTAGE",
        "SECONDS",
        name="metric_value_type",
    )

    metric_category.create(
        op.get_bind(),
        checkfirst=True,
    )

    metric_status.create(
        op.get_bind(),
        checkfirst=True,
    )

    metric_value_type.create(
        op.get_bind(),
        checkfirst=True,
    )

    op.create_table(
        "metric_definitions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "key",
            sa.String(length=150),
            nullable=False,
        ),
        sa.Column(
            "name",
            sa.String(length=200),
            nullable=False,
        ),
        sa.Column(
            "description",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "category",
            postgresql.ENUM(
                "CUSTOMER",
                "COMPLIANCE",
                "OPERATIONS",
                name="metric_category",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "value_type",
            postgresql.ENUM(
                "PERCENTAGE",
                "SECONDS",
                name="metric_value_type",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "definition",
            postgresql.JSONB(),
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM(
                "ACTIVE",
                "INACTIVE",
                name="metric_status",
                create_type=False,
            ),
            nullable=False,
            server_default="ACTIVE",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "key",
            name="uq_metric_definitions_key",
        ),
    )

    op.create_index(
        "ix_metric_definitions_key",
        "metric_definitions",
        ["key"],
    )

    op.create_index(
        "ix_metric_definitions_category",
        "metric_definitions",
        ["category"],
    )

    op.create_index(
        "ix_metric_definitions_status",
        "metric_definitions",
        ["status"],
    )

    op.create_table(
        "metric_results",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "metric_definition_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "period_start",
            sa.Date(),
            nullable=False,
        ),
        sa.Column(
            "period_end",
            sa.Date(),
            nullable=False,
        ),
        sa.Column(
            "value",
            sa.Numeric(
                precision=20,
                scale=6,
            ),
            nullable=True,
        ),
        sa.Column(
            "calculated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["metric_definition_id"],
            ["metric_definitions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "metric_definition_id",
            "period_start",
            "period_end",
            name="uq_metric_results_definition_period",
        ),
    )

    op.create_index(
        "ix_metric_results_metric_definition_id",
        "metric_results",
        ["metric_definition_id"],
    )

    op.create_index(
        "ix_metric_results_period_start",
        "metric_results",
        ["period_start"],
    )

    op.create_index(
        "ix_metric_results_period_end",
        "metric_results",
        ["period_end"],
    )

    definitions = [
        {
            "id": uuid.uuid4(),
            "key": "customer_registration_rate",
            "name": "Customer Registration Rate",
            "description": (
                "Percentage of the customer base that was registered "
                "during the requested reporting period."
            ),
            "category": "CUSTOMER",
            "value_type": "PERCENTAGE",
            "definition": {
                "type": "ratio",
                "numerator": "customer_registrations",
                "denominator": "customer_opening_base",
                "multiplier": 100,
                "precision": 2,
            },
            "status": "ACTIVE",
        },
        {
            "id": uuid.uuid4(),
            "key": "verification_completion_rate",
            "name": "Verification Completion Rate",
            "description": (
                "Percentage of verification cases completed during "
                "the reporting period relative to verification cases created "
                "during that period."
            ),
            "category": "CUSTOMER",
            "value_type": "PERCENTAGE",
            "definition": {
                "type": "ratio",
                "numerator": "verification_cases_completed",
                "denominator": "verification_cases_created",
                "multiplier": 100,
                "precision": 2,
            },
            "status": "ACTIVE",
        },
        {
            "id": uuid.uuid4(),
            "key": "verification_approval_rate",
            "name": "Verification Approval Rate",
            "description": (
                "Percentage of completed verification cases that were approved."
            ),
            "category": "CUSTOMER",
            "value_type": "PERCENTAGE",
            "definition": {
                "type": "ratio",
                "numerator": "verification_approvals",
                "denominator": "verification_cases_completed",
                "multiplier": 100,
                "precision": 2,
            },
            "status": "ACTIVE",
        },
        {
            "id": uuid.uuid4(),
            "key": "average_compliance_review_time",
            "name": "Average Compliance Review Time",
            "description": (
                "Average elapsed time in seconds from compliance case "
                "creation until case closure during the reporting period."
            ),
            "category": "COMPLIANCE",
            "value_type": "SECONDS",
            "definition": {
                "type": "average_duration",
                "measure": "compliance_review_time_seconds",
                "precision": 2,
            },
            "status": "ACTIVE",
        },
        {
            "id": uuid.uuid4(),
            "key": "alert_resolution_time",
            "name": "Alert Resolution Time",
            "description": (
                "Average elapsed time in seconds from AML alert case "
                "creation until closure during the reporting period."
            ),
            "category": "COMPLIANCE",
            "value_type": "SECONDS",
            "definition": {
                "type": "average_duration",
                "measure": "alert_resolution_time_seconds",
                "precision": 2,
            },
            "status": "ACTIVE",
        },
        {
            "id": uuid.uuid4(),
            "key": "high_risk_customer_percentage",
            "name": "High-Risk Customer Percentage",
            "description": (
                "Percentage of customers classified as HIGH or CRITICAL "
                "risk at the end of the reporting period."
            ),
            "category": "COMPLIANCE",
            "value_type": "PERCENTAGE",
            "definition": {
                "type": "ratio",
                "numerator": "high_risk_customers_at_end",
                "denominator": "customers_at_end",
                "multiplier": 100,
                "precision": 2,
            },
            "status": "ACTIVE",
        },
        {
            "id": uuid.uuid4(),
            "key": "task_completion_rate",
            "name": "Task Completion Rate",
            "description": (
                "Percentage of tasks completed during the reporting period "
                "relative to tasks created during that period."
            ),
            "category": "OPERATIONS",
            "value_type": "PERCENTAGE",
            "definition": {
                "type": "ratio",
                "numerator": "tasks_completed",
                "denominator": "tasks_created",
                "multiplier": 100,
                "precision": 2,
            },
            "status": "ACTIVE",
        },
        {
            "id": uuid.uuid4(),
            "key": "sla_compliance_percentage",
            "name": "SLA Compliance Percentage",
            "description": (
                "Percentage of completed tasks that were completed within SLA."
            ),
            "category": "OPERATIONS",
            "value_type": "PERCENTAGE",
            "definition": {
                "type": "ratio",
                "numerator": "tasks_completed_within_sla",
                "denominator": "tasks_completed",
                "multiplier": 100,
                "precision": 2,
            },
            "status": "ACTIVE",
        },
    ]

    op.bulk_insert(
        sa.table(
            "metric_definitions",
            sa.column(
                "id",
                postgresql.UUID(as_uuid=True),
            ),
            sa.column("key", sa.String()),
            sa.column("name", sa.String()),
            sa.column("description", sa.Text()),
            sa.column("category", metric_category),
            sa.column("value_type", metric_value_type),
            sa.column("definition", postgresql.JSONB()),
            sa.column("status", metric_status),
        ),
        definitions,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_metric_results_period_end",
        table_name="metric_results",
    )

    op.drop_index(
        "ix_metric_results_period_start",
        table_name="metric_results",
    )

    op.drop_index(
        "ix_metric_results_metric_definition_id",
        table_name="metric_results",
    )

    op.drop_table("metric_results")

    op.drop_index(
        "ix_metric_definitions_status",
        table_name="metric_definitions",
    )

    op.drop_index(
        "ix_metric_definitions_category",
        table_name="metric_definitions",
    )

    op.drop_index(
        "ix_metric_definitions_key",
        table_name="metric_definitions",
    )

    op.drop_table("metric_definitions")

    op.execute(
        "DROP TYPE IF EXISTS metric_value_type",
    )

    op.execute(
        "DROP TYPE IF EXISTS metric_status",
    )

    op.execute(
        "DROP TYPE IF EXISTS metric_category",
    )
