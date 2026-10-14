"""Platform-level partner onboarding requests and workflow history."""

import uuid
from datetime import datetime
from uuid import UUID

from sqlalchemy import (
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
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.utils.enums import PartnerOnboardingStatus

PARTNER_ONBOARDING_STATUS_ENUM = Enum(
    PartnerOnboardingStatus, name="partner_onboarding_status"
)


class PartnerOnboarding(Base):
    """A platform-level request to onboard a new enterprise partner.

    This model intentionally has no ``tenant_id`` column: a prospective
    partner does not belong to a provisioned tenant yet. All management reads
    are therefore restricted to platform administrators at the API layer.
    ``activated_tenant_id`` links the request to the tenant created on approval
    without applying regular tenant filtering to the onboarding queue itself.
    """

    __tablename__ = "partner_onboarding"
    __table_args__ = (
        UniqueConstraint(
            "activated_tenant_id",
            name="uq_partner_onboarding_activated_tenant_id",
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


class PartnerOnboardingHistory(Base):
    """Append-only timeline of assignment and partner onboarding decisions."""

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
        PARTNER_ONBOARDING_STATUS_ENUM,
        nullable=True,
    )
    status: Mapped[PartnerOnboardingStatus] = mapped_column(
        PARTNER_ONBOARDING_STATUS_ENUM,
        nullable=False,
    )
    changed_by: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    onboarding: Mapped[PartnerOnboarding] = relationship(back_populates="history")
