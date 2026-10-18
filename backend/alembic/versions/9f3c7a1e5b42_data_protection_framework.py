# mypy: ignore-errors

"""Add tenant-scoped data protection controls and encrypted sensitive fields.

Revision ID: 9f3c7a1e5b42
Revises: 7d8e91c2a4f6
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "9f3c7a1e5b42"
down_revision: Union[str, Sequence[str], None] = "7d8e91c2a4f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "data_protection_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("retention_days", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("legal_basis", sa.String(length=255), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "resource_type",
            name="uq_data_protection_policy_tenant_resource",
        ),
    )
    op.create_index(
        "ix_data_protection_policies_tenant_enabled",
        "data_protection_policies",
        ["tenant_id", "enabled"],
    )
    op.create_index(
        "ix_data_protection_policies_tenant_id",
        "data_protection_policies",
        ["tenant_id"],
    )

    op.create_table(
        "data_legal_holds",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("released_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["released_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_data_legal_holds_tenant_resource",
        "data_legal_holds",
        ["tenant_id", "resource_type", "resource_id"],
    )
    op.create_index(
        "ix_data_legal_holds_tenant_active", "data_legal_holds", ["tenant_id", "active"]
    )
    op.create_index("ix_data_legal_holds_tenant_id", "data_legal_holds", ["tenant_id"])

    op.create_table(
        "data_deletion_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("requested_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("approved_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["approved_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_data_deletion_requests_tenant_status",
        "data_deletion_requests",
        ["tenant_id", "status"],
    )
    op.create_index(
        "ix_data_deletion_requests_tenant_resource",
        "data_deletion_requests",
        ["tenant_id", "resource_type", "resource_id"],
    )
    op.create_index(
        "ix_data_deletion_requests_tenant_id", "data_deletion_requests", ["tenant_id"]
    )

    op.create_table(
        "data_protection_audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_data_protection_audit_tenant_created",
        "data_protection_audit_events",
        ["tenant_id", "created_at"],
    )
    op.create_index(
        "ix_data_protection_audit_tenant_action",
        "data_protection_audit_events",
        ["tenant_id", "action"],
    )
    op.create_index(
        "ix_data_protection_audit_events_tenant_id",
        "data_protection_audit_events",
        ["tenant_id"],
    )

    # Ciphertext must fit; encrypted values are longer than the original VARCHAR limit.
    for name, size, nullable in (
        ("address_line_1", 255, False),
        ("address_line_2", 255, True),
        ("city", 100, False),
        ("state", 100, True),
        ("country", 100, False),
        ("postal_code", 30, True),
    ):
        op.alter_column(
            "customer_addresses",
            name,
            existing_type=sa.String(length=size),
            type_=sa.Text(),
            existing_nullable=nullable,
        )

    for name in (
        "first_name",
        "middle_name",
        "last_name",
        "nationality",
        "document_number",
    ):
        op.alter_column(
            "document_extractions",
            name,
            existing_type=sa.String(length=100),
            type_=sa.Text(),
            existing_nullable=True,
        )
    op.alter_column(
        "document_extractions",
        "date_of_birth",
        existing_type=sa.Date(),
        type_=sa.Text(),
        existing_nullable=True,
        postgresql_using="date_of_birth::text",
    )
    op.alter_column(
        "document_extractions",
        "expiry_date",
        existing_type=sa.Date(),
        type_=sa.Text(),
        existing_nullable=True,
        postgresql_using="expiry_date::text",
    )

    op.alter_column(
        "customer_documents",
        "file_name",
        existing_type=sa.String(length=255),
        type_=sa.Text(),
        existing_nullable=False,
    )
    op.alter_column(
        "files",
        "original_filename",
        existing_type=sa.String(length=255),
        type_=sa.Text(),
        existing_nullable=False,
    )
    op.alter_column(
        "customer_audit_logs",
        "old_value",
        existing_type=sa.JSON(),
        type_=sa.Text(),
        existing_nullable=True,
        postgresql_using="old_value::text",
    )
    op.alter_column(
        "customer_audit_logs",
        "new_value",
        existing_type=sa.JSON(),
        type_=sa.Text(),
        existing_nullable=True,
        postgresql_using="new_value::text",
    )


def downgrade() -> None:
    # Deliberately fail closed: ciphertext is also used for local files. Restoring an
    # old application binary alone would make encrypted files/fields unreadable.
    raise RuntimeError(
        "Data-protection migration downgrade is intentionally disabled. "
        "Restore a verified pre-migration backup and decrypt/restore "
        "storage using the documented recovery plan."
    )
