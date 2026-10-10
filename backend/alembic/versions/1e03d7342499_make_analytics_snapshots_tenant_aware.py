# mypy: ignore-errors

"""make analytics snapshots tenant aware

Revision ID: 1e03d7342499
Revises: 683f1f0daf98
Create Date: 2026-10-10 02:53:31.627528

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1e03d7342499"
down_revision: Union[str, Sequence[str], None] = "683f1f0daf98"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLES = (
    ("analytics_customer_daily", "snapshot_date"),
    ("analytics_compliance_daily", "snapshot_date"),
    ("analytics_operations_daily", "snapshot_date"),
    ("analytics_customer_monthly", "month_start"),
    ("analytics_compliance_monthly", "month_start"),
    ("analytics_operations_monthly", "month_start"),
)


def upgrade() -> None:
    for table_name, period_column in TABLES:
        op.add_column(
            table_name,
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                nullable=True,
            ),
        )

        op.add_column(
            table_name,
            sa.Column(
                "tenant_id",
                postgresql.UUID(as_uuid=True),
                nullable=True,
            ),
        )

        # Populate IDs for every existing historical row.
        op.execute(
            sa.text(f"UPDATE {table_name} SET id = gen_random_uuid() WHERE id IS NULL")
        )

        op.alter_column(
            table_name,
            "id",
            existing_type=postgresql.UUID(as_uuid=True),
            nullable=False,
        )

        op.drop_constraint(
            f"{table_name}_pkey",
            table_name,
            type_="primary",
        )

        op.create_primary_key(
            f"pk_{table_name}",
            table_name,
            ["id"],
        )

        op.create_foreign_key(
            f"fk_{table_name}_tenant_id_tenants",
            table_name,
            "tenants",
            ["tenant_id"],
            ["id"],
            ondelete="CASCADE",
        )

        op.create_index(
            f"uq_{table_name}_tenant_{period_column}",
            table_name,
            ["tenant_id", period_column],
            unique=True,
            postgresql_where=sa.text("tenant_id IS NOT NULL"),
        )


def downgrade() -> None:
    # Tenant-specific aggregates cannot be safely merged back into
    # the previous one-row-per-date schema. Delete them on downgrade,
    # preserving legacy rows whose tenant_id is NULL.
    for table_name, period_column in reversed(TABLES):
        op.execute(sa.text(f"DELETE FROM {table_name} WHERE tenant_id IS NOT NULL"))

        op.drop_index(
            f"uq_{table_name}_tenant_{period_column}",
            table_name=table_name,
        )

        op.drop_constraint(
            f"fk_{table_name}_tenant_id_tenants",
            table_name,
            type_="foreignkey",
        )

        op.drop_constraint(
            f"pk_{table_name}",
            table_name,
            type_="primary",
        )

        op.create_primary_key(
            f"{table_name}_pkey",
            table_name,
            [period_column],
        )

        op.drop_column(table_name, "tenant_id")
        op.drop_column(table_name, "id")
