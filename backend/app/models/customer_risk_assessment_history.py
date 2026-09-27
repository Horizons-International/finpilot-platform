from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.utils.enums import CustomerRiskLevel


class CustomerRiskAssessmentHistory(Base):
    __tablename__ = "customer_risk_assessment_history"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    customer_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "customers.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    risk_level: Mapped[CustomerRiskLevel] = mapped_column(
        Enum(
            CustomerRiskLevel,
            name="customer_risk_level",
            create_type=False,
        ),
        nullable=False,
        index=True,
    )

    risk_score: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    risk_category: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    assessed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    assessment_source: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    calculation_details: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
