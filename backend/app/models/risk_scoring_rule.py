import uuid
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Enum, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.utils.enums import RiskRuleOperator


class RiskScoringRule(Base):
    __tablename__ = "risk_scoring_rules"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    factor_key: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    operator: Mapped[RiskRuleOperator] = mapped_column(
        Enum(
            RiskRuleOperator,
            name="risk_rule_operator",
        ),
        nullable=False,
    )

    expected_value: Mapped[Any] = mapped_column(
        JSONB,
        nullable=True,
    )

    score_points: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    priority: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        index=True,
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
