"""Tenant-scoped customer feedback and a shared product roadmap."""

import uuid
from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ProductRoadmapItem(Base):
    """Shared roadmap item; visibility decides what tenant users may see."""

    __tablename__ = "product_roadmap_items"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PROPOSED', 'PLANNED', 'IN_PROGRESS', 'SHIPPED', 'DECLINED')",
            name="ck_product_roadmap_items_status",
        ),
        CheckConstraint(
            "visibility IN ('PUBLIC', 'INTERNAL')",
            name="ck_product_roadmap_items_visibility",
        ),
        Index("ix_product_roadmap_items_visibility_status", "visibility", "status"),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="PROPOSED", server_default="PROPOSED"
    )
    visibility: Mapped[str] = mapped_column(
        String(16), nullable=False, default="INTERNAL", server_default="INTERNAL"
    )
    target_release: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_by: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    creator = relationship("User", foreign_keys=[created_by])


class CustomerFeedback(Base):
    """Feedback submitted by a customer tenant."""

    __tablename__ = "customer_feedback"
    __table_args__ = (
        CheckConstraint(
            "category IN ('FEATURE_REQUEST', 'IMPROVEMENT', 'PROBLEM', 'COMPLAINT')",
            name="ck_customer_feedback_category",
        ),
        CheckConstraint(
            "priority IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')",
            name="ck_customer_feedback_priority",
        ),
        CheckConstraint(
            "status IN ('SUBMITTED', 'UNDER_REVIEW', 'ACCEPTED', 'PLANNED', "
            "'IN_PROGRESS', 'COMPLETED', 'DECLINED', 'DUPLICATE')",
            name="ck_customer_feedback_status",
        ),
        UniqueConstraint("id", "tenant_id", name="uq_customer_feedback_id_tenant"),
        Index("ix_customer_feedback_tenant_created", "tenant_id", "created_at"),
        Index("ix_customer_feedback_tenant_status", "tenant_id", "status"),
        Index("ix_customer_feedback_category_priority", "category", "priority"),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(24), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(
        String(16), nullable=False, default="MEDIUM", server_default="MEDIUM"
    )
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="SUBMITTED", server_default="SUBMITTED"
    )
    submitted_by: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    reviewed_by: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    roadmap_item_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("product_roadmap_items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    roadmap_item = relationship("ProductRoadmapItem", foreign_keys=[roadmap_item_id])
    submitter = relationship("User", foreign_keys=[submitted_by])
    reviewer = relationship("User", foreign_keys=[reviewed_by])


class CustomerFeedbackHistory(Base):
    """Append-only lifecycle events linked to a feedback item and its tenant."""

    __tablename__ = "customer_feedback_history"
    __table_args__ = (
        ForeignKeyConstraint(
            ["feedback_id", "tenant_id"],
            ["customer_feedback.id", "customer_feedback.tenant_id"],
            name="fk_customer_feedback_history_feedback_tenant",
            ondelete="CASCADE",
        ),
        Index(
            "ix_customer_feedback_history_feedback_created",
            "feedback_id",
            "created_at",
        ),
        Index("ix_customer_feedback_history_tenant_created", "tenant_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    feedback_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    old_value: Mapped[str | None] = mapped_column(String(500), nullable=True)
    new_value: Mapped[str | None] = mapped_column(String(500), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed_by: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    feedback = relationship("CustomerFeedback")
    actor = relationship("User", foreign_keys=[changed_by])
