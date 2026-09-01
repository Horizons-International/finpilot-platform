# mypy: ignore-errors

"""update enum types

Revision ID: f8a343441b4b
Revises: 17c3621e5559
Create Date: 2026-09-01 16:40:16.122312

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f8a343441b4b"
down_revision: Union[str, Sequence[str], None] = "17c3621e5559"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Change customer status history columns to customer_status enum."""

    # Convert old_status from customerstatus to customer_status.
    op.execute(
        """
        ALTER TABLE customer_status_history
        ALTER COLUMN old_status
        TYPE customer_status
        USING old_status::text::customer_status
        """
    )

    # Convert new_status from customerstatus to customer_status.
    op.execute(
        """
        ALTER TABLE customer_status_history
        ALTER COLUMN new_status
        TYPE customer_status
        USING new_status::text::customer_status
        """
    )

    # customerstatus is no longer needed after both columns
    # have been converted.
    op.execute(
        """
        DROP TYPE customerstatus
        """
    )


def downgrade() -> None:
    """Restore the customerstatus enum."""

    # Recreate the old enum type.
    op.execute(
        """
        CREATE TYPE customerstatus AS ENUM (
            'NEW',
            'PENDING_VERIFICATION',
            'VERIFIED',
            'SUSPENDED',
            'REJECTED'
        )
        """
    )

    # Convert old_status back.
    op.execute(
        """
        ALTER TABLE customer_status_history
        ALTER COLUMN old_status
        TYPE customerstatus
        USING old_status::text::customerstatus
        """
    )

    # Convert new_status back.
    op.execute(
        """
        ALTER TABLE customer_status_history
        ALTER COLUMN new_status
        TYPE customerstatus
        USING new_status::text::customerstatus
        """
    )
