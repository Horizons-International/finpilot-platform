"""Tenant-scoped, explainable compliance case priority history."""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.utils.enums import ComplianceCasePriority


class CasePriority(Base):
    __tablename__ = "case_priorities"
    __table_args__ = (
        CheckConstraint(
            "priority_score >= 0 AND priority_score <= 100",
            name="ck_case_priorities_score_range",
        ),
        Index(
            "ix_case_priorities_tenant_case_created",
            "tenant_id",
            "case_id",
            "created_at",
        ),
        Index(
            "ix_case_priorities_tenant_level_score",
            "tenant_id",
            "priority_level",
            "priority_score",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    case_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("compliance_cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    priority_level: Mapped[ComplianceCasePriority] = mapped_column(
        Enum(
            ComplianceCasePriority,
            name="compliance_case_priority",
            create_constraint=False,
        ),
        nullable=False,
        index=True,
    )
    priority_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    risk_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )

    case = relationship("ComplianceCase", foreign_keys=[case_id])
    tenant = relationship("Tenant")
