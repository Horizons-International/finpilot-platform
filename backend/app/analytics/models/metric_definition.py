import uuid
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, Enum, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.utils.enums import (
    MetricCategory,
    MetricStatus,
    MetricValueType,
)


class MetricDefinition(Base):
    __tablename__ = "metric_definitions"

    __table_args__ = (
        UniqueConstraint(
            "key",
            name="uq_metric_definitions_key",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    key: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    category: Mapped[MetricCategory] = mapped_column(
        Enum(
            MetricCategory,
            name="metric_category",
        ),
        nullable=False,
        index=True,
    )

    value_type: Mapped[MetricValueType] = mapped_column(
        Enum(
            MetricValueType,
            name="metric_value_type",
        ),
        nullable=False,
    )

    definition: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
    )

    status: Mapped[MetricStatus] = mapped_column(
        Enum(
            MetricStatus,
            name="metric_status",
        ),
        nullable=False,
        default=MetricStatus.ACTIVE,
        server_default=MetricStatus.ACTIVE.value,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
