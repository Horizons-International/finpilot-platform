# mypy: ignore-errors

"""add verifivation document type to audit event type

Revision ID: 1e809eeb540c
Revises: 4f8ecc00028e
Create Date: 2026-09-06 22:07:39.634133

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1e809eeb540c"
down_revision: Union[str, Sequence[str], None] = "4f8ecc00028e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        "ALTER TYPE auditeventtype ADD VALUE IF NOT EXISTS "
        "'VERIFICATION_DOCUMENT_TYPE_CREATED'"
    )
    op.execute(
        "ALTER TYPE auditeventtype ADD VALUE IF NOT EXISTS "
        "'VERIFICATION_DOCUMENT_TYPE_UPDATED'"
    )
    op.execute(
        "ALTER TYPE auditeventtype ADD VALUE IF NOT EXISTS "
        "'VERIFICATION_DOCUMENT_TYPE_STATUS_CHANGED'"
    )


def downgrade() -> None:
    """Downgrade schema."""
    pass
