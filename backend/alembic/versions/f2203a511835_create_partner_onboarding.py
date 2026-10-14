# mypy: ignore-errors
"""Create platform-level partner onboarding workflow and history."""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "f2203a511835"
down_revision: Union[str, Sequence[str], None] = "b1e8d5c7a941"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_ONBOARDING_STATUSES = (
    "REQUESTED",
    "BUSINESS_INFORMATION",
    "COMPLIANCE_REVIEW",
    "TECHNICAL_SETUP",
    "API_CREDENTIALS",
    "ACTIVE",
    "REJECTED",
)
_AUDIT_EVENTS = (
    "PARTNER_ONBOARDING_CREATED",
    "PARTNER_ONBOARDING_UPDATED",
    "PARTNER_ONBOARDING_ASSIGNED",
    "PARTNER_ONBOARDING_STAGE_CHANGED",
    "PARTNER_ONBOARDING_APPROVED",
    "PARTNER_ONBOARDING_REJECTED",
)


def upgrade() -> None:
    for event_name in _AUDIT_EVENTS:
        op.execute(f"ALTER TYPE auditeventtype ADD VALUE IF NOT EXISTS '{event_name}'")

    onboarding_status = postgresql.ENUM(
        *_ONBOARDING_STATUSES,
        name="partner_onboarding_status",
        create_type=False,
    )
    onboarding_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "partner_onboarding",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_name", sa.String(length=200), nullable=False),
        sa.Column("legal_name", sa.String(length=200), nullable=True),
        sa.Column("registration_number", sa.String(length=100), nullable=True),
        sa.Column("tax_identification_number", sa.String(length=100), nullable=True),
        sa.Column("industry", sa.String(length=100), nullable=True),
        sa.Column("business_description", sa.Text(), nullable=True),
        sa.Column("contact_name", sa.String(length=200), nullable=False),
        sa.Column("contact_email", sa.String(length=255), nullable=False),
        sa.Column("contact_phone", sa.String(length=30), nullable=True),
        sa.Column("website", sa.String(length=500), nullable=True),
        sa.Column("country", sa.String(length=2), nullable=False),
        sa.Column(
            "status",
            onboarding_status,
            server_default="REQUESTED",
            nullable=False,
        ),
        sa.Column("assigned_to", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("activated_tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("internal_notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["assigned_to"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["activated_tenant_id"], ["tenants.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "activated_tenant_id", name="uq_partner_onboarding_activated_tenant_id"
        ),
    )
    op.create_index(
        "ix_partner_onboarding_status",
        "partner_onboarding",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_partner_onboarding_assigned_to",
        "partner_onboarding",
        ["assigned_to"],
        unique=False,
    )
    op.create_index(
        "ix_partner_onboarding_created_at",
        "partner_onboarding",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_partner_onboarding_status_created",
        "partner_onboarding",
        ["status", "created_at"],
        unique=False,
    )
    op.create_index(
        "uq_partner_onboarding_non_rejected_contact_email",
        "partner_onboarding",
        ["contact_email"],
        unique=True,
        postgresql_where=sa.text("status <> 'REJECTED'"),
    )

    op.create_table(
        "partner_onboarding_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("onboarding_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(length=30), nullable=False),
        sa.Column("previous_status", onboarding_status, nullable=True),
        sa.Column("status", onboarding_status, nullable=False),
        sa.Column("changed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["onboarding_id"], ["partner_onboarding.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["changed_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_partner_onboarding_history_onboarding_id",
        "partner_onboarding_history",
        ["onboarding_id"],
        unique=False,
    )
    op.create_index(
        "ix_partner_onboarding_history_parent_created",
        "partner_onboarding_history",
        ["onboarding_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_partner_onboarding_history_parent_created",
        table_name="partner_onboarding_history",
    )
    op.drop_index(
        "ix_partner_onboarding_history_onboarding_id",
        table_name="partner_onboarding_history",
    )
    op.drop_table("partner_onboarding_history")
    op.drop_index(
        "uq_partner_onboarding_non_rejected_contact_email",
        table_name="partner_onboarding",
    )
    op.drop_index(
        "ix_partner_onboarding_status_created", table_name="partner_onboarding"
    )
    op.drop_index("ix_partner_onboarding_created_at", table_name="partner_onboarding")
    op.drop_index("ix_partner_onboarding_assigned_to", table_name="partner_onboarding")
    op.drop_index("ix_partner_onboarding_status", table_name="partner_onboarding")
    op.drop_table("partner_onboarding")
    onboarding_status = postgresql.ENUM(
        *_ONBOARDING_STATUSES,
        name="partner_onboarding_status",
    )
    onboarding_status.drop(op.get_bind(), checkfirst=True)
    # PostgreSQL enum labels already added to auditeventtype are intentionally
    # retained by downgrade; removing labels is not generally supported safely.
