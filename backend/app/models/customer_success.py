"""Tenant-scoped customer-success profiles, usage snapshots and relationship history."""

import uuid
from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
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


class CustomerSuccessProfile(Base):
    """Customer lifecycle record owned by one customer-success team tenant.

    ``tenant_id`` is the tenant that owns/manages the relationship record;
    ``customer_tenant_id`` is the enterprise customer being managed. Keeping
    those identities separate permits a provider team to manage its accounts
    without moving or duplicating the customer's production data.
    """

    __tablename__ = "customer_success_profiles"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "customer_tenant_id",
            name="uq_customer_success_profile_customer",
        ),
        UniqueConstraint(
            "id", "tenant_id", name="uq_customer_success_profile_id_tenant"
        ),
        CheckConstraint(
            "account_status IN ('TRIAL', 'ACTIVE', 'AT_RISK', 'PAUSED', 'CHURNED')",
            name="ck_customer_success_profile_account_status",
        ),
        CheckConstraint(
            "implementation_stage IN ('NOT_STARTED', 'CONFIGURATION', 'INTEGRATION', "
            "'TESTING', 'READY_FOR_PRODUCTION', 'LIVE')",
            name="ck_customer_success_profile_implementation_stage",
        ),
        CheckConstraint(
            "health_score >= 0 AND health_score <= 100",
            name="ck_customer_success_profile_health_score",
        ),
        CheckConstraint(
            "health_band IN ('HEALTHY', 'NEEDS_ATTENTION', 'AT_RISK')",
            name="ck_customer_success_profile_health_band",
        ),
        Index(
            "ix_customer_success_profile_tenant_health",
            "tenant_id",
            "health_band",
        ),
        Index(
            "ix_customer_success_profile_tenant_status",
            "tenant_id",
            "account_status",
        ),
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
    customer_tenant_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    account_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="TRIAL", server_default="TRIAL"
    )
    implementation_stage: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="NOT_STARTED",
        server_default="NOT_STARTED",
    )
    assigned_manager_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    success_plan: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_contacted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    health_score: Mapped[int] = mapped_column(
        Integer, nullable=False, default=100, server_default="100"
    )
    health_band: Mapped[str] = mapped_column(
        String(24), nullable=False, default="HEALTHY", server_default="HEALTHY"
    )
    health_score_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
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

    owner_tenant = relationship("Tenant", foreign_keys=[tenant_id])
    customer_tenant = relationship("Tenant", foreign_keys=[customer_tenant_id])
    assigned_manager = relationship("User", foreign_keys=[assigned_manager_id])
    creator = relationship("User", foreign_keys=[created_by])
    usage_snapshots: Mapped[list["CustomerSuccessUsageSnapshot"]] = relationship(
        back_populates="profile",
        cascade="all, delete-orphan",
        order_by="CustomerSuccessUsageSnapshot.period_start.desc()",
    )
    support_interactions: Mapped[list["CustomerSuccessSupportInteraction"]] = (
        relationship(
            back_populates="profile",
            cascade="all, delete-orphan",
            order_by="CustomerSuccessSupportInteraction.created_at.desc()",
        )
    )
    history: Mapped[list["CustomerSuccessHistory"]] = relationship(
        back_populates="profile",
        cascade="all, delete-orphan",
        order_by="CustomerSuccessHistory.created_at.desc()",
    )

    @property
    def customer_tenant_name(self) -> str | None:
        return self.customer_tenant.name if self.customer_tenant is not None else None

    @property
    def assigned_manager_name(self) -> str | None:
        if self.assigned_manager is None:
            return None
        full_name = (
            f"{self.assigned_manager.first_name} {self.assigned_manager.last_name}"
        )
        return full_name.strip()


class CustomerSuccessUsageSnapshot(Base):
    """Explicit time-bounded usage sample; does not rewrite billing counters."""

    __tablename__ = "customer_success_usage_snapshots"
    __table_args__ = (
        ForeignKeyConstraint(
            ["profile_id", "tenant_id"],
            ["customer_success_profiles.id", "customer_success_profiles.tenant_id"],
            name="fk_customer_success_usage_profile_tenant",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "profile_id", "period_start", name="uq_customer_success_usage_period"
        ),
        CheckConstraint(
            "period_end >= period_start", name="ck_customer_success_usage_period_dates"
        ),
        CheckConstraint(
            (
                "active_users >= 0 AND licensed_users >= 0 "
                "AND active_users <= licensed_users"
            ),
            name="ck_customer_success_usage_user_counts",
        ),
        CheckConstraint(
            "api_calls >= 0 AND (api_call_limit IS NULL OR api_call_limit >= 0)",
            name="ck_customer_success_usage_api_counts",
        ),
        CheckConstraint(
            "active_features >= 0 AND available_features >= 0 "
            "AND active_features <= available_features",
            name="ck_customer_success_usage_feature_counts",
        ),
        Index(
            "ix_customer_success_usage_profile_period",
            "profile_id",
            "period_start",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=False, index=True
    )
    profile_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=False
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    active_users: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    licensed_users: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    api_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    api_call_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    active_features: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    available_features: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source: Mapped[str] = mapped_column(
        String(32), nullable=False, default="MANUAL", server_default="MANUAL"
    )
    recorded_by: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    profile: Mapped[CustomerSuccessProfile] = relationship(
        back_populates="usage_snapshots"
    )
    recorder = relationship("User", foreign_keys=[recorded_by])


class CustomerSuccessSupportInteraction(Base):
    """Support case or customer touchpoint maintained in the success record."""

    __tablename__ = "customer_success_support_interactions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["profile_id", "tenant_id"],
            ["customer_success_profiles.id", "customer_success_profiles.tenant_id"],
            name="fk_customer_success_support_profile_tenant",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            (
                "category IN ('INCIDENT', 'QUESTION', 'REQUEST', 'BILLING', "
                "'INTEGRATION', 'TRAINING', 'OTHER')"
            ),
            name="ck_customer_success_support_category",
        ),
        CheckConstraint(
            "severity IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')",
            name="ck_customer_success_support_severity",
        ),
        CheckConstraint(
            (
                "status IN ('OPEN', 'IN_PROGRESS', 'WAITING_CUSTOMER', "
                "'RESOLVED', 'CLOSED')"
            ),
            name="ck_customer_success_support_status",
        ),
        Index(
            "ix_customer_success_support_profile_status",
            "profile_id",
            "status",
        ),
        Index(
            "ix_customer_success_support_tenant_created",
            "tenant_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=False, index=True
    )
    profile_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=False
    )
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(
        String(20), nullable=False, default="QUESTION", server_default="QUESTION"
    )
    severity: Mapped[str] = mapped_column(
        String(12), nullable=False, default="MEDIUM", server_default="MEDIUM"
    )
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="OPEN", server_default="OPEN"
    )
    assigned_to: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    profile: Mapped[CustomerSuccessProfile] = relationship(
        back_populates="support_interactions"
    )
    assignee = relationship("User", foreign_keys=[assigned_to])
    creator = relationship("User", foreign_keys=[created_by])


class CustomerSuccessHistory(Base):
    """Append-only customer relationship timeline, including notes and changes."""

    __tablename__ = "customer_success_history"
    __table_args__ = (
        ForeignKeyConstraint(
            ["profile_id", "tenant_id"],
            ["customer_success_profiles.id", "customer_success_profiles.tenant_id"],
            name="fk_customer_success_history_profile_tenant",
            ondelete="CASCADE",
        ),
        Index(
            "ix_customer_success_history_profile_created",
            "profile_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=False, index=True
    )
    profile_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    actor_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    profile: Mapped[CustomerSuccessProfile] = relationship(back_populates="history")
    actor = relationship("User", foreign_keys=[actor_id])
