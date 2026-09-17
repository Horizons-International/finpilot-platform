# mypy: ignore-errors

"""add knowledge document audit events

Revision ID: c9b1040eeb80
Revises: be362e345cfe
Create Date: 2026-09-17 20:26:47.821992

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9b1040eeb80"
down_revision: Union[str, Sequence[str], None] = "be362e345cfe"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        "ALTER TYPE auditeventtype ADD VALUE IF NOT EXISTS 'KNOWLEDGE_DOCUMENT_CREATED'"
    )
    op.execute(
        "ALTER TYPE auditeventtype "
        "ADD VALUE IF NOT EXISTS 'KNOWLEDGE_DOCUMENT_VERSION_CREATED'"
    )
    op.execute(
        "ALTER TYPE auditeventtype "
        "ADD VALUE IF NOT EXISTS 'KNOWLEDGE_DOCUMENT_ACTIVATED'"
    )
    op.execute(
        "ALTER TYPE auditeventtype "
        "ADD VALUE IF NOT EXISTS 'KNOWLEDGE_DOCUMENT_DEACTIVATED'"
    )


def downgrade() -> None:
    """Downgrade schema."""
    pass
