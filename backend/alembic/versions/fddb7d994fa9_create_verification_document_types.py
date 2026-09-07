# mypy: ignore-errors

"""create verification document types

Revision ID: fddb7d994fa9
Revises: 9aed960c9a57
Create Date: 2026-09-06 14:00:29.144219

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "fddb7d994fa9"
down_revision: Union[str, Sequence[str], None] = "9aed960c9a57"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


document_category = postgresql.ENUM(
    "IDENTITY",
    "ADDRESS",
    name="document_category",
    create_type=False,
)


def upgrade() -> None:
    document_category.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "verification_document_types",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "name",
            sa.String(length=100),
            nullable=False,
        ),
        sa.Column(
            "category",
            document_category,
            nullable=False,
        ),
        sa.Column(
            "supported_countries",
            postgresql.ARRAY(sa.String(length=2)),
            nullable=False,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_index(
        "ix_verification_document_types_name",
        "verification_document_types",
        ["name"],
        unique=False,
    )

    op.create_index(
        "ix_verification_document_types_category",
        "verification_document_types",
        ["category"],
        unique=False,
    )

    op.create_index(
        "ix_verification_document_types_is_active",
        "verification_document_types",
        ["is_active"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_verification_document_types_is_active",
        table_name="verification_document_types",
    )

    op.drop_index(
        "ix_verification_document_types_category",
        table_name="verification_document_types",
    )

    op.drop_index(
        "ix_verification_document_types_name",
        table_name="verification_document_types",
    )

    op.drop_table("verification_document_types")

    document_category.drop(op.get_bind(), checkfirst=True)
