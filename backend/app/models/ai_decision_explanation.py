"""Persisted, tenant-scoped explanations for FinPilot AI decisions."""

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
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class AIDecisionExplanation(Base):
    """Immutable, point-in-time rationale for one AI or rules-engine decision.

    ``decision_id`` is intentionally not a foreign key: decisions are produced by
    several existing tables, and ``decision_type`` disambiguates their UUIDs.
    """

    __tablename__ = "ai_decision_explanations"
    __table_args__ = (
        CheckConstraint(
            "confidence_score IS NULL OR "
            "(confidence_score >= 0 AND confidence_score <= 1)",
            name="ck_ai_decision_explanations_confidence_range",
        ),
        Index(
            "ix_ai_decision_explanations_tenant_decision_created",
            "tenant_id",
            "decision_type",
            "decision_id",
            "created_at",
        ),
        Index(
            "ix_ai_decision_explanations_tenant_created",
            "tenant_id",
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
    decision_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    decision_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=False, index=True
    )
    factors: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    data_sources: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    risk_indicators: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    confidence_score: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 4), nullable=True
    )
    recommendation_reason: Mapped[str] = mapped_column(Text, nullable=False)
    model_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    provider_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    decision_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    tenant = relationship("Tenant")
