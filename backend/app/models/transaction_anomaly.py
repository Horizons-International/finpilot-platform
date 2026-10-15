"""Tenant-scoped transaction anomaly events and observed activity facts."""

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


class TransactionAnomalyActivity(Base):
    """Transaction facts retained so later evaluations have a useful baseline."""

    __tablename__ = "transaction_anomaly_activity"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "transaction_id",
            name="uq_transaction_anomaly_activity_tenant_transaction",
        ),
        CheckConstraint(
            "amount > 0", name="ck_transaction_anomaly_activity_amount_positive"
        ),
        Index(
            "ix_transaction_anomaly_activity_tenant_customer_time",
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
    destination_country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    beneficiary_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    transaction_type: Mapped[str] = mapped_column(
        String(100), nullable=False, default="TRANSFER", server_default="TRANSFER"
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    tenant = relationship("Tenant")
    customer = relationship("Customer")


class TransactionAnomaly(Base):
    """One auditable anomaly event associated with a customer transaction."""

    __tablename__ = "transaction_anomalies"
    __table_args__ = (
        CheckConstraint(
            "risk_score >= 0 AND risk_score <= 100",
            name="ck_transaction_anomalies_risk_score_range",
        ),
        CheckConstraint(
            "risk_level IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')",
            name="ck_transaction_anomalies_risk_level",
        ),
        Index(
            "ix_transaction_anomalies_tenant_customer_created",
            "tenant_id",
            "customer_id",
            "created_at",
        ),
        Index(
            "ix_transaction_anomalies_tenant_transaction",
            "tenant_id",
            "transaction_id",
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
    transaction_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=False, index=True
    )
    anomaly_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    risk_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    summary: Mapped[str] = mapped_column(String(1000), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    tenant = relationship("Tenant")
    customer = relationship("Customer")
