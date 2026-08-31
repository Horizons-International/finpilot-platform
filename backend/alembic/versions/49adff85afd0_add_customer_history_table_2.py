"""add customer history table 2

Revision ID: 49adff85afd0
Revises: dfa8ef64bada
Create Date: 2026-08-31 21:38:15.921869

"""

from typing import Sequence, Union

from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "49adff85afd0"
down_revision: Union[str, Sequence[str], None] = "dfa8ef64bada"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

customer_status_enum = postgresql.ENUM(
    "NEW",
    "PENDING_VERIFICATION",
    "VERIFIED",
    "SUSPENDED",
    "REJECTED",
    name="customer_status",
)


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
