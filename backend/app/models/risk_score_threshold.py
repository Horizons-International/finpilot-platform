import uuid
from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Enum, Integer, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.utils.enums import CustomerRiskLevel


class RiskScoreThreshold(Base):
    __tablename__ = "risk_score_thresholds"

    __table_args__ = (
        UniqueConstraint(
            "risk_level",
            name="uq_risk_score_thresholds_risk_level",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
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

    min_score: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    max_score: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
