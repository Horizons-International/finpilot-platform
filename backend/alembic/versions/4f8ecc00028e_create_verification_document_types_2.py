# mypy: ignore-errors

"""create verification document types 2

Revision ID: 4f8ecc00028e
Revises: fddb7d994fa9
Create Date: 2026-09-06 14:12:00.809436

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

document_category = postgresql.ENUM(
    "IDENTITY",
    "ADDRESS",
    name="document_category",
    create_type=False,
)

# revision identifiers, used by Alembic.
revision: str = "4f8ecc00028e"
down_revision: Union[str, Sequence[str], None] = "fddb7d994fa9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    verification_document_types = sa.table(
        "verification_document_types",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("name", sa.String()),
        sa.column("category", document_category),
        sa.column(
            "supported_countries",
            postgresql.ARRAY(sa.String(length=2)),
        ),
        sa.column("is_active", sa.Boolean()),
    )

    op.bulk_insert(
        verification_document_types,
        [
            {
                "id": "00000000-0000-0000-0000-000000000001",
                "name": "Passport",
                "category": "IDENTITY",
                "supported_countries": [],
                "is_active": True,
            },
            {
                "id": "00000000-0000-0000-0000-000000000002",
                "name": "National ID",
                "category": "IDENTITY",
                "supported_countries": [],
                "is_active": True,
            },
            {
                "id": "00000000-0000-0000-0000-000000000003",
                "name": "Driving License",
                "category": "IDENTITY",
                "supported_countries": [],
                "is_active": True,
            },
            {
                "id": "00000000-0000-0000-0000-000000000004",
                "name": "Proof of Address",
                "category": "ADDRESS",
                "supported_countries": [],
                "is_active": True,
            },
        ],
    )


def downgrade() -> None:
    """Downgrade schema."""
    pass
