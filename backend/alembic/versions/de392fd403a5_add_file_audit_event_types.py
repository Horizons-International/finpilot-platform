# mypy: ignore-errors

"""add file audit event types

Revision ID: de392fd403a5
Revises: ff0d168f8209
Create Date: 2026-08-21 01:20:17.117806

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "de392fd403a5"
down_revision: Union[str, Sequence[str], None] = "ff0d168f8209"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TYPE auditeventtype ADD VALUE IF NOT EXISTS 'FILE_UPLOAD'")
    op.execute("ALTER TYPE auditeventtype ADD VALUE IF NOT EXISTS 'FILE_DOWNLOAD'")
    op.execute("ALTER TYPE auditeventtype ADD VALUE IF NOT EXISTS 'FILE_DELETE'")
    op.execute("ALTER TYPE auditeventtype ADD VALUE IF NOT EXISTS 'USER_CREATED'")
    op.execute("ALTER TYPE auditeventtype ADD VALUE IF NOT EXISTS 'USER_UPDATED'")
    op.execute("ALTER TYPE auditeventtype ADD VALUE IF NOT EXISTS 'USER_DELETED'")
    op.execute(
        "ALTER TYPE auditeventtype ADD VALUE IF NOT EXISTS 'USER_STATUS_CHANGED'"
    )


def downgrade() -> None:
    """Downgrade schema."""
    pass
