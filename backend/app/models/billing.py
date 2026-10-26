"""Pricing plans and durable invoice snapshots for FinPilot billing."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
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


class BillingPlan(Base):
    """Global commercial price book; plan terms are snapshotted on invoice lines."""

    __tablename__ = "billing_plans"
    __table_args__ = (
        UniqueConstraint("name", name="uq_billing_plans_name"),
        CheckConstraint(
            "pricing_model IN ('SUBSCRIPTION', 'USAGE_BASED', 'ENTERPRISE')",
            name="ck_billing_plans_pricing_model",
        ),
        CheckConstraint(
            "billing_interval IN ('MONTHLY', 'ANNUAL', 'CUSTOM')",
            name="ck_billing_plans_billing_interval",
        ),
        CheckConstraint(
            "status IN ('ACTIVE', 'INACTIVE')", name="ck_billing_plans_status"
        ),
        CheckConstraint("base_fee >= 0", name="ck_billing_plans_base_fee_nonnegative"),
        CheckConstraint(
            "currency ~ '^[A-Z]{3}$'", name="ck_billing_plans_currency_format"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    pricing_model: Mapped[str] = mapped_column(String(24), nullable=False)
    billing_interval: Mapped[str] = mapped_column(String(16), nullable=False)
    subscription_tier: Mapped[str] = mapped_column(
        String(32), nullable=False, default="starter", server_default="starter"
    )
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="USD", server_default="USD"
    )
    base_fee: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0.00"), server_default="0"
    )
    # JSON values for rates are serialized as decimal strings to avoid float drift.
    unit_rates: Mapped[dict[str, str]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    # Monthly included units per billable metric; used independently from quota limits.
    included_units: Mapped[dict[str, int]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    limits: Mapped[dict[str, int | None]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    features: Mapped[dict[str, bool]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="ACTIVE",
        server_default="ACTIVE",
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


class Invoice(Base):
    """Invoice header.

    Monetary amounts and line descriptions are immutable snapshots.
    """

    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint("invoice_number", name="uq_invoices_invoice_number"),
        UniqueConstraint(
            "tenant_id",
            "period_start",
            "period_end",
            name="uq_invoices_tenant_period",
        ),
        UniqueConstraint("id", "tenant_id", name="uq_invoices_id_tenant"),
        CheckConstraint(
            "status IN ('DRAFT', 'ISSUED', 'PAID', 'VOID')",
            name="ck_invoices_status",
        ),
        CheckConstraint("amount >= 0", name="ck_invoices_amount_nonnegative"),
        CheckConstraint("period_end >= period_start", name="ck_invoices_valid_period"),
        Index("ix_invoices_tenant_created", "tenant_id", "created_at"),
        Index("ix_invoices_tenant_period", "tenant_id", "period_start", "period_end"),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    subscription_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("subscriptions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    billing_plan_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("billing_plans.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    invoice_number: Mapped[str] = mapped_column(String(40), nullable=False)
    plan_name_snapshot: Mapped[str] = mapped_column(String(100), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="DRAFT", server_default="DRAFT", index=True
    )
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    line_items: Mapped[list["InvoiceLineItem"]] = relationship(
        back_populates="invoice",
        cascade="all, delete-orphan",
        order_by="InvoiceLineItem.id",
    )


class InvoiceLineItem(Base):
    """Per-period charge snapshot. It intentionally stores no live rate reference."""

    __tablename__ = "invoice_line_items"
    __table_args__ = (
        ForeignKeyConstraint(
            ["invoice_id", "tenant_id"],
            ["invoices.id", "invoices.tenant_id"],
            name="fk_invoice_line_items_invoice_tenant",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "quantity >= 0", name="ck_invoice_line_items_quantity_nonnegative"
        ),
        CheckConstraint(
            "unit_price >= 0", name="ck_invoice_line_items_unit_price_nonnegative"
        ),
        CheckConstraint("amount >= 0", name="ck_invoice_line_items_amount_nonnegative"),
        Index("ix_invoice_line_items_tenant_invoice", "tenant_id", "invoice_id"),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    invoice_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=False
    )
    description: Mapped[str] = mapped_column(String(240), nullable=False)
    metric: Mapped[str | None] = mapped_column(String(32), nullable=True)
    quantity: Mapped[int] = mapped_column(BigInteger, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    invoice: Mapped[Invoice] = relationship(back_populates="line_items")
