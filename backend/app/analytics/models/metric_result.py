import uuid
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MetricResult(Base):
    __tablename__ = "metric_results"

    __table_args__ = (
        UniqueConstraint(
            "metric_definition_id",
            "period_start",
            "period_end",
            name="uq_metric_results_definition_period",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    metric_definition_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "metric_definitions.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    period_start: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )

    period_end: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )

    value: Mapped[Decimal | None] = mapped_column(
        Numeric(
            precision=20,
            scale=6,
        ),
        nullable=True,
    )

    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
