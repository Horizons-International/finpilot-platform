"""Tenant-scoped AI transaction-risk results and the transactions they assessed."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class TransactionRiskAnalysis(Base):
    """Auditable AI recommendation for one batch of customer transactions."""

    __tablename__ = "transaction_risk_analyses"
    __table_args__ = (
        CheckConstraint(
            "risk_score >= 0 AND risk_score <= 100",
            name="ck_transaction_risk_analyses_score_range",
        ),
        CheckConstraint(
            "risk_level IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')",
            name="ck_transaction_risk_analyses_level",
        ),
        Index(
            "ix_transaction_risk_analyses_tenant_customer_created",
            "tenant_id",
            "customer_id",
            "created_at",
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
    customer_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_by: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    compliance_case_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("compliance_cases.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    risk_score: Mapped[int] = mapped_column(nullable=False)
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(String(5000), nullable=False)
    recommended_action: Mapped[str] = mapped_column(String(3000), nullable=False)
    risk_factors: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    confidence: Mapped[float] = mapped_column(nullable=False)
    provider_name: Mapped[str] = mapped_column(String(100), nullable=False)
    model_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    context_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    transaction_summary: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    baseline_summary: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    ai_response: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    transactions: Mapped[list["TransactionRiskTransaction"]] = relationship(
        back_populates="analysis",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="TransactionRiskTransaction.occurred_at",
    )
    tenant = relationship("Tenant")
    customer = relationship("Customer")
    creator = relationship("User", foreign_keys=[created_by])


class TransactionRiskTransaction(Base):
    """Tenant-owned transaction facts retained to support future baselines."""

    __tablename__ = "transaction_risk_transactions"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "transaction_id",
            name="uq_transaction_risk_transactions_tenant_txn",
        ),
        Index(
            "ix_transaction_risk_transactions_customer_time",
            "tenant_id",
            "customer_id",
            "occurred_at",
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
    analysis_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("transaction_risk_analyses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    customer_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    transaction_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    destination_country: Mapped[str] = mapped_column(String(100), nullable=False)
    transaction_type: Mapped[str] = mapped_column(String(100), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    analysis: Mapped[TransactionRiskAnalysis] = relationship(
        back_populates="transactions"
    )
    tenant = relationship("Tenant")
