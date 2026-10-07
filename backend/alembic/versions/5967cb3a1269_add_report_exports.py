# mypy: ignore-errors

"""add report exports

Revision ID: 5967cb3a1269
Revises: 0ce9fc6ed4fc
Create Date: 2026-10-07 17:46:30.548322

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5967cb3a1269"
down_revision: Union[str, Sequence[str], None] = "0ce9fc6ed4fc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "report_exports",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "report_type",
            postgresql.ENUM(
                "CUSTOMER",
                "VERIFICATION",
                "COMPLIANCE",
                "OPERATIONAL_PERFORMANCE",
                name="report_type",
                create_type=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "format",
            postgresql.ENUM(
                "CSV",
                "EXCEL",
                "PDF",
                name="report_export_format",
                create_type=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "requested_by",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "filters",
            postgresql.JSONB(),
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM(
                "REQUESTED",
                "PROCESSING",
                "COMPLETED",
                "FAILED",
                name="report_export_status",
                create_type=True,
            ),
            nullable=False,
            server_default="REQUESTED",
        ),
        sa.Column(
            "filename",
            sa.String(length=255),
            nullable=True,
        ),
        sa.Column(
            "content_type",
            sa.String(length=100),
            nullable=True,
        ),
        sa.Column(
            "storage_path",
            sa.String(length=500),
            nullable=True,
        ),
        sa.Column(
            "file_size",
            sa.BigInteger(),
            nullable=True,
        ),
        sa.Column(
            "row_count",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "error_message",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["requested_by"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_report_exports_report_type",
        "report_exports",
        ["report_type"],
        unique=False,
    )

    op.create_index(
        "ix_report_exports_requested_by",
        "report_exports",
        ["requested_by"],
        unique=False,
    )

    op.create_index(
        "ix_report_exports_status",
        "report_exports",
        ["status"],
        unique=False,
    )

    op.create_index(
        "ix_report_exports_created_at",
        "report_exports",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_report_exports_created_at",
        table_name="report_exports",
    )

    op.drop_index(
        "ix_report_exports_status",
        table_name="report_exports",
    )

    op.drop_index(
        "ix_report_exports_requested_by",
        table_name="report_exports",
    )

    op.drop_index(
        "ix_report_exports_report_type",
        table_name="report_exports",
    )

    op.drop_table("report_exports")

    op.execute("DROP TYPE IF EXISTS report_export_status")
    op.execute("DROP TYPE IF EXISTS report_export_format")
    op.execute("DROP TYPE IF EXISTS report_type")
