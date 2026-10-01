# mypy: ignore_errors

"""seed customer onboarding workflow

Revision ID: 86665af4a6d6
Revises: d705b42a9aa9
Create Date: 2026-10-01 19:48:52.148635

"""

import uuid
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "86665af4a6d6"
down_revision: Union[str, Sequence[str], None] = "d705b42a9aa9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Workflow step failure support.
    op.execute(
        "ALTER TYPE workflow_step_execution_status ADD VALUE IF NOT EXISTS 'FAILED'"
    )

    # Workflow audit events.
    audit_events = [
        "WORKFLOW_STEP_FAILED",
        "WORKFLOW_STEP_RETRIED",
        "WORKFLOW_EXECUTION_FAILED",
    ]

    for event_name in audit_events:
        op.execute(f"ALTER TYPE auditeventtype ADD VALUE IF NOT EXISTS '{event_name}'")

    workflows = sa.table(
        "workflows",
        sa.column("id", sa.UUID()),
        sa.column("name", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("status", sa.Enum()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )

    workflow_steps = sa.table(
        "workflow_steps",
        sa.column("id", sa.UUID()),
        sa.column("workflow_id", sa.UUID()),
        sa.column("name", sa.String()),
        sa.column("order_number", sa.Integer()),
        sa.column("assigned_role", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )

    connection = op.get_bind()

    existing_workflow = connection.execute(
        sa.text("SELECT id FROM workflows WHERE name = :name LIMIT 1"),
        {
            "name": "Customer Onboarding",
        },
    ).scalar_one_or_none()

    if existing_workflow is not None:
        return

    workflow_id = uuid.uuid4()

    connection.execute(
        workflows.insert().values(
            id=workflow_id,
            name="Customer Onboarding",
            description=(
                "Standard customer onboarding journey from "
                "account creation through approval."
            ),
            status="ACTIVE",
        )
    )

    steps = [
        (
            "Create Account",
            1,
            "Reviewer",
        ),
        (
            "Customer Information",
            2,
            "Reviewer",
        ),
        (
            "Address Collection",
            3,
            "Reviewer",
        ),
        (
            "Document Upload",
            4,
            "Reviewer",
        ),
        (
            "Identity Verification",
            5,
            "Reviewer",
        ),
        (
            "Compliance Review",
            6,
            "Compliance Officer",
        ),
        (
            "Approved",
            7,
            "Compliance Officer",
        ),
    ]

    connection.execute(
        workflow_steps.insert(),
        [
            {
                "id": uuid.uuid4(),
                "workflow_id": workflow_id,
                "name": name,
                "order_number": order_number,
                "assigned_role": assigned_role,
            }
            for name, order_number, assigned_role in steps
        ],
    )


def downgrade() -> None:
    connection = op.get_bind()

    workflow_id = connection.execute(
        sa.text("SELECT id FROM workflows WHERE name = :name LIMIT 1"),
        {
            "name": "Customer Onboarding",
        },
    ).scalar_one_or_none()

    if workflow_id is None:
        return

    # Do not delete a workflow that has already been executed.
    execution_count = connection.execute(
        sa.text(
            "SELECT COUNT(*) FROM workflow_executions WHERE workflow_id = :workflow_id"
        ),
        {
            "workflow_id": workflow_id,
        },
    ).scalar_one()

    if execution_count:
        return

    connection.execute(
        sa.text("DELETE FROM workflow_steps WHERE workflow_id = :workflow_id"),
        {
            "workflow_id": workflow_id,
        },
    )

    connection.execute(
        sa.text("DELETE FROM workflows WHERE id = :workflow_id"),
        {
            "workflow_id": workflow_id,
        },
    )

    # PostgreSQL does not support removing an individual enum value.
    # The FAILED enum value intentionally remains.
