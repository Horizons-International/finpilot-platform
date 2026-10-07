# mypy: ignore-errors

"""add risk predictions

Revision ID: 0ce9fc6ed4fc
Revises: 6f05d1794b4d
Create Date: 2026-10-07 16:25:15.139710

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0ce9fc6ed4fc"
down_revision: Union[str, Sequence[str], None] = "6f05d1794b4d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "risk_predictions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "customer_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "model_version",
            sa.String(length=100),
            nullable=False,
        ),
        sa.Column(
            "risk_probability",
            sa.Numeric(
                precision=10,
                scale=8,
            ),
            nullable=False,
        ),
        sa.Column(
            "features",
            postgresql.JSONB(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_risk_predictions_customer_id",
        "risk_predictions",
        ["customer_id"],
    )

    op.create_index(
        "ix_risk_predictions_model_version",
        "risk_predictions",
        ["model_version"],
    )

    op.create_index(
        "ix_risk_predictions_created_at",
        "risk_predictions",
        ["created_at"],
    )

    op.execute(
        "ALTER TYPE auditeventtype ADD VALUE IF NOT EXISTS 'RISK_PREDICTION_CREATED'"
    )


def downgrade() -> None:
    op.drop_index(
        "ix_risk_predictions_created_at",
        table_name="risk_predictions",
    )

    op.drop_index(
        "ix_risk_predictions_model_version",
        table_name="risk_predictions",
    )

    op.drop_index(
        "ix_risk_predictions_customer_id",
        table_name="risk_predictions",
    )

    op.drop_table("risk_predictions")
