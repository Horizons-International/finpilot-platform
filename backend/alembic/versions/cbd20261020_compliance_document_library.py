# mypy: ignore-errors

"""Create compliance documents, immutable versions, approvals, and evidence."""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "cbd20261020"
down_revision: Union[str, Sequence[str], None] = "a8c91e27d4f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    document_status = postgresql.ENUM(
        "DRAFT",
        "IN_REVIEW",
        "APPROVED",
        "REJECTED",
        "ARCHIVED",
        name="compliance_document_status",
        create_type=False,
    )
    approval_status = postgresql.ENUM(
        "PENDING",
        "APPROVED",
        "REJECTED",
        name="compliance_approval_status",
        create_type=False,
    )
    document_status.create(bind, checkfirst=True)
    approval_status.create(bind, checkfirst=True)

    op.create_table(
        "compliance_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("status", document_status, nullable=False),
        sa.Column("owner", postgresql.UUID(as_uuid=True), nullable=False),
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
        sa.ForeignKeyConstraint(["owner"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_compliance_documents_tenant_id", "compliance_documents", ["tenant_id"]
    )
    op.create_index(
        "ix_compliance_documents_category", "compliance_documents", ["category"]
    )
    op.create_index(
        "ix_compliance_documents_status", "compliance_documents", ["status"]
    )
    op.create_index("ix_compliance_documents_owner", "compliance_documents", ["owner"])
    op.create_index(
        "ix_compliance_documents_created_at", "compliance_documents", ["created_at"]
    )

    op.create_table(
        "compliance_document_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("file_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("change_summary", sa.String(length=2000), nullable=True),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["document_id"], ["compliance_documents.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["file_id"], ["files.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "document_id", "version", name="uq_compliance_doc_version"
        ),
        sa.UniqueConstraint("file_id", name="uq_compliance_doc_version_file"),
    )
    op.create_index(
        "ix_compliance_document_versions_tenant_id",
        "compliance_document_versions",
        ["tenant_id"],
    )
    op.create_index(
        "ix_compliance_document_versions_document_id",
        "compliance_document_versions",
        ["document_id"],
    )
    op.create_index(
        "ix_compliance_document_versions_created_at",
        "compliance_document_versions",
        ["created_at"],
    )

    op.create_table(
        "compliance_document_approvals",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", approval_status, nullable=False),
        sa.Column("requested_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("request_comment", sa.Text(), nullable=True),
        sa.Column("review_comment", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["document_id"], ["compliance_documents.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_compliance_document_approvals_tenant_id",
        "compliance_document_approvals",
        ["tenant_id"],
    )
    op.create_index(
        "ix_compliance_document_approvals_document_id",
        "compliance_document_approvals",
        ["document_id"],
    )
    op.create_index(
        "ix_compliance_document_approvals_status",
        "compliance_document_approvals",
        ["status"],
    )
    op.create_index(
        "ix_compliance_document_approvals_created_at",
        "compliance_document_approvals",
        ["created_at"],
    )

    op.create_table(
        "compliance_evidence_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("evidence_type", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("source_reference", sa.String(length=1000), nullable=False),
        sa.Column("collected_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "collected_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["document_id"], ["compliance_documents.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["version_id"], ["compliance_document_versions.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["collected_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_compliance_evidence_records_tenant_id",
        "compliance_evidence_records",
        ["tenant_id"],
    )
    op.create_index(
        "ix_compliance_evidence_records_document_id",
        "compliance_evidence_records",
        ["document_id"],
    )
    op.create_index(
        "ix_compliance_evidence_records_evidence_type",
        "compliance_evidence_records",
        ["evidence_type"],
    )
    op.create_index(
        "ix_compliance_evidence_records_created_at",
        "compliance_evidence_records",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_table("compliance_evidence_records")
    op.drop_table("compliance_document_approvals")
    op.drop_table("compliance_document_versions")
    op.drop_table("compliance_documents")
    postgresql.ENUM(name="compliance_approval_status").drop(
        op.get_bind(), checkfirst=True
    )
    postgresql.ENUM(name="compliance_document_status").drop(
        op.get_bind(), checkfirst=True
    )
