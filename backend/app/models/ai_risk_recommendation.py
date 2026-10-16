"""Persisted, tenant-scoped AI-assisted compliance recommendations."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class AIRiskRecommendation(Base):
    """An immutable point-in-time recommendation based on tenant-owned evidence."""

    __tablename__ = "ai_risk_recommendations"
    __table_args__ = (
        CheckConstraint(
            "risk_score >= 0 AND risk_score <= 100",
            name="ck_ai_risk_recommendations_score_range",
        ),
        CheckConstraint(
            "risk_level IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')",
            name="ck_ai_risk_recommendations_risk_level",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_ai_risk_recommendations_confidence_range",
        ),
        Index(
            "ix_ai_risk_recommendations_tenant_customer_created",
            "tenant_id",
            "customer_id",
            "created_at",
        ),
        Index(
            "ix_ai_risk_recommendations_tenant_case_created",
            "tenant_id",
            "compliance_case_id",
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
    compliance_case_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("compliance_cases.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_by: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    risk_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False)
    recommendation: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_action: Mapped[str] = mapped_column(Text, nullable=False)
    required_review_type: Mapped[str] = mapped_column(String(64), nullable=False)
    risk_factors: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    provider_name: Mapped[str] = mapped_column(
        String(100), nullable=False, default="deterministic_rules"
    )
    model_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    tenant = relationship("Tenant")
    customer = relationship("Customer")
    compliance_case = relationship("ComplianceCase")
    creator = relationship("User", foreign_keys=[created_by])
