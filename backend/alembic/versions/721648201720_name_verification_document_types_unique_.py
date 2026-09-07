# mypy: ignore-errors

"""name verification document types unique constraint

Revision ID: 721648201720
Revises: 1e809eeb540c
Create Date: 2026-09-07 01:40:51.542319

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "721648201720"
down_revision: Union[str, Sequence[str], None] = "1e809eeb540c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "verification_document_types_name_key",
        "verification_document_types",
        type_="unique",
    )

    op.create_unique_constraint(
        "uq_verification_document_types_name",
        "verification_document_types",
        ["name"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_verification_document_types_name",
        "verification_document_types",
        type_="unique",
    )

    op.create_unique_constraint(
        "verification_document_types_name_key",
        "verification_document_types",
        ["name"],
    )
