"""Platform-level partner onboarding requests, evidence, invitees and history."""

import uuid
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.utils.enums import PartnerOnboardingStatus

PARTNER_ONBOARDING_STATUS_ENUM = Enum(
    PartnerOnboardingStatus, name="partner_onboarding_status"
)


class PartnerOnboarding(Base):
    """Pre-tenant onboarding request for a prospective enterprise customer.

    A prospective organization cannot have a tenant_id until activation creates
    its tenant. These records are platform-level and all management operations
    are therefore restricted to platform administrators in the API layer.
    """

    __tablename__ = "partner_onboarding"
    __table_args__ = (
        UniqueConstraint(
            "activated_tenant_id",
            name="uq_partner_onboarding_activated_tenant_id",
        ),
        UniqueConstraint(
            "portal_token_hash",
            name="uq_partner_onboarding_portal_token_hash",
        ),
        Index("ix_partner_onboarding_status_created", "status", "created_at"),
        Index(
            "uq_partner_onboarding_non_rejected_contact_email",
            "contact_email",
            unique=True,
            postgresql_where=text("status <> 'REJECTED'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_name: Mapped[str] = mapped_column(String(200), nullable=False)
    legal_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    registration_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tax_identification_number: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )
    industry: Mapped[str | None] = mapped_column(String(100), nullable=True)
    business_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    contact_name: Mapped[str] = mapped_column(String(200), nullable=False)
    contact_email: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    country: Mapped[str] = mapped_column(String(2), nullable=False)
    status: Mapped[PartnerOnboardingStatus] = mapped_column(
        PARTNER_ONBOARDING_STATUS_ENUM,
        nullable=False,
        default=PartnerOnboardingStatus.REQUESTED,
        server_default=PartnerOnboardingStatus.REQUESTED.value,
        index=True,
    )
    assigned_to: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    activated_tenant_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="SET NULL"),
        nullable=True,
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    internal_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Customer-facing portal credentials are stored as hashes only.
    portal_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    portal_token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Must not contain passwords, tokens, private keys, or other secrets.
    technical_setup: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    technical_setup_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    history: Mapped[list["PartnerOnboardingHistory"]] = relationship(
        back_populates="onboarding",
        cascade="all, delete-orphan",
        order_by="PartnerOnboardingHistory.created_at",
    )
    documents: Mapped[list["PartnerOnboardingDocument"]] = relationship(
        back_populates="onboarding",
        cascade="all, delete-orphan",
        order_by="PartnerOnboardingDocument.created_at",
    )
    administrators: Mapped[list["PartnerOnboardingAdministrator"]] = relationship(
        back_populates="onboarding",
        cascade="all, delete-orphan",
        order_by="PartnerOnboardingAdministrator.created_at",
    )


class PartnerOnboardingHistory(Base):
    """Append-only timeline of assignment, stage, and onboarding decisions."""

    __tablename__ = "partner_onboarding_history"
    __table_args__ = (
        Index(
            "ix_partner_onboarding_history_parent_created",
            "onboarding_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    onboarding_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("partner_onboarding.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    previous_status: Mapped[PartnerOnboardingStatus | None] = mapped_column(
        PARTNER_ONBOARDING_STATUS_ENUM, nullable=True
    )
    status: Mapped[PartnerOnboardingStatus] = mapped_column(
        PARTNER_ONBOARDING_STATUS_ENUM, nullable=False
    )
    changed_by: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    onboarding: Mapped[PartnerOnboarding] = relationship(back_populates="history")


class PartnerOnboardingDocument(Base):
    """Document metadata and review decision for a pre-tenant onboarding request."""

    __tablename__ = "partner_onboarding_documents"
    __table_args__ = (
        CheckConstraint(
            "review_status IN ('PENDING_REVIEW', 'APPROVED', 'REJECTED')",
            name="ck_partner_onboarding_document_review_status",
        ),
        Index(
            "ix_partner_onboarding_documents_parent_type_created",
            "onboarding_id",
            "document_type",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    onboarding_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("partner_onboarding.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_type: Mapped[str] = mapped_column(String(60), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    review_status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="PENDING_REVIEW"
    )
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    onboarding: Mapped[PartnerOnboarding] = relationship(back_populates="documents")


class PartnerOnboardingAdministrator(Base):
    """Proposed first administrator; becomes a tenant invitation on activation."""

    __tablename__ = "partner_onboarding_administrators"
    __table_args__ = (
        UniqueConstraint(
            "onboarding_id", "email", name="uq_partner_onboarding_admin_email"
        ),
        UniqueConstraint(
            "invitation_token_hash",
            name="uq_partner_onboarding_admin_invitation_token_hash",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'INVITED')",
            name="ck_partner_onboarding_admin_status",
        ),
        Index(
            "ix_partner_onboarding_administrators_parent_created",
            "onboarding_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    onboarding_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("partner_onboarding.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    department: Mapped[str | None] = mapped_column(String(100), nullable=True)
    invitation_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="PENDING"
    )
    invited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    onboarding: Mapped[PartnerOnboarding] = relationship(
        back_populates="administrators"
    )
