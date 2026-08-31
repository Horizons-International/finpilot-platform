# mypy: ignore-errors

"""add customer history table 4

Revision ID: 105af7b498b8
Revises: 03dfb34b4892
Create Date: 2026-08-31 21:59:48.946259

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "105af7b498b8"
down_revision: Union[str, Sequence[str], None] = "03dfb34b4892"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TYPE customer_status RENAME VALUE 'ACTIVE' to 'NEW'")
    op.execute(
        "ALTER TYPE customer_status RENAME VALUE 'INACTIVE' to 'PENDING_VERIFICATION'"
    )
    op.execute("ALTER TYPE customer_status ADD VALUE IF NOT EXISTS 'VERIFIED'")
    op.execute("ALTER TYPE customer_status ADD VALUE IF NOT EXISTS 'SUSPENDED'")
    op.execute("ALTER TYPE customer_status ADD VALUE IF NOT EXISTS 'REJECTED'")


def downgrade() -> None:
    pass
