# mypy: ignore-errors

"""upadate audit event type

Revision ID: 17c3621e5559
Revises: 105af7b498b8
Create Date: 2026-08-31 22:31:50.747179

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "17c3621e5559"
down_revision: Union[str, Sequence[str], None] = "105af7b498b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE auditeventtype ADD VALUE IF NOT EXISTS 'CUSTOMER_STATUS_CHANGED'"
    )


def downgrade() -> None:
    pass
