# mypy: ignore-errors

"""enable pgvector extension

Revision ID: e01628670ad9
Revises: c9b1040eeb80
Create Date: 2026-09-17 22:46:50.849021

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e01628670ad9"
down_revision: Union[str, Sequence[str], None] = "c9b1040eeb80"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS vector")
