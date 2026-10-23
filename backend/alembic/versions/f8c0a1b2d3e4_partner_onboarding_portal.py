# mypy: ignore-errors
"""Add self-service onboarding portal, documents, nominations, and setup tracking."""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "f8c0a1b2d3e4"
down_revision: Union[str, Sequence[str], None] = "cbd20261020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "partner_onboarding",
        sa.Column("portal_token_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "partner_onboarding",
        sa.Column("portal_token_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "partner_onboarding",
        sa.Column(
            "technical_setup",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "partner_onboarding",
        sa.Column(
            "technical_setup_completed_at", sa.DateTime(timezone=True), nullable=True
        ),
    )
    op.create_unique_constraint(
        "uq_partner_onboarding_portal_token_hash",
        "partner_onboarding",
        ["portal_token_hash"],
    )

    op.create_table(
        "partner_onboarding_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("onboarding_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_type", sa.String(length=60), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("storage_path", sa.String(length=1000), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "review_status",
            sa.String(length=20),
            server_default="PENDING_REVIEW",
            nullable=False,
        ),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "review_status IN ('PENDING_REVIEW', 'APPROVED', 'REJECTED')",
            name="ck_partner_onboarding_document_review_status",
        ),
        sa.ForeignKeyConstraint(
            ["onboarding_id"], ["partner_onboarding.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_partner_onboarding_documents_onboarding_id",
        "partner_onboarding_documents",
        ["onboarding_id"],
    )
    op.create_index(
        "ix_partner_onboarding_documents_parent_type_created",
        "partner_onboarding_documents",
        ["onboarding_id", "document_type", "created_at"],
    )

    op.create_table(
        "partner_onboarding_administrators",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("onboarding_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column("department", sa.String(length=100), nullable=True),
        sa.Column("invitation_token_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "status", sa.String(length=20), server_default="PENDING", nullable=False
        ),
        sa.Column("invited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'INVITED')",
            name="ck_partner_onboarding_admin_status",
        ),
        sa.ForeignKeyConstraint(
            ["onboarding_id"], ["partner_onboarding.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "onboarding_id", "email", name="uq_partner_onboarding_admin_email"
        ),
        sa.UniqueConstraint(
            "invitation_token_hash",
            name="uq_partner_onboarding_admin_invitation_token_hash",
        ),
    )
    op.create_index(
        "ix_partner_onboarding_administrators_onboarding_id",
        "partner_onboarding_administrators",
        ["onboarding_id"],
    )
    op.create_index(
        "ix_partner_onboarding_administrators_parent_created",
        "partner_onboarding_administrators",
        ["onboarding_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_partner_onboarding_administrators_parent_created",
        table_name="partner_onboarding_administrators",
    )
    op.drop_index(
        "ix_partner_onboarding_administrators_onboarding_id",
        table_name="partner_onboarding_administrators",
    )
    op.drop_table("partner_onboarding_administrators")

    op.drop_index(
        "ix_partner_onboarding_documents_parent_type_created",
        table_name="partner_onboarding_documents",
    )
    op.drop_index(
        "ix_partner_onboarding_documents_onboarding_id",
        table_name="partner_onboarding_documents",
    )
    op.drop_table("partner_onboarding_documents")

    op.drop_constraint(
        "uq_partner_onboarding_portal_token_hash",
        "partner_onboarding",
        type_="unique",
    )
    op.drop_column("partner_onboarding", "technical_setup_completed_at")
    op.drop_column("partner_onboarding", "technical_setup")
    op.drop_column("partner_onboarding", "portal_token_expires_at")
    op.drop_column("partner_onboarding", "portal_token_hash")
