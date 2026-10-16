"""Tenant-scoped aggregate monitoring metrics for AI models."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class AIModelMetric(Base):
    __tablename__ = "ai_model_metrics"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "model_name",
            "model_version",
            name="uq_ai_model_metrics_tenant_model_version",
        ),
        CheckConstraint(
            "request_count >= 0",
            name="ck_ai_model_metrics_request_count_nonnegative",
        ),
        CheckConstraint(
            "success_count >= 0",
            name="ck_ai_model_metrics_success_count_nonnegative",
        ),
        CheckConstraint(
            "error_count >= 0",
            name="ck_ai_model_metrics_error_count_nonnegative",
        ),
        CheckConstraint(
            "total_response_time_ms >= 0",
            name="ck_ai_model_metrics_total_latency_nonnegative",
        ),
        CheckConstraint(
            "feedback_count >= 0",
            name="ck_ai_model_metrics_feedback_count_nonnegative",
        ),
        CheckConstraint(
            "accuracy_measurement_count >= 0",
            name="ck_ai_model_metrics_accuracy_count_nonnegative",
        ),
        Index(
            "ix_ai_model_metrics_tenant_updated",
            "tenant_id",
            "updated_at",
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
    model_name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    model_version: Mapped[str] = mapped_column(
        String(100), nullable=False, default="unspecified", server_default="unspecified"
    )
    request_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    success_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    error_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    total_response_time_ms: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    feedback_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    feedback_rating_sum: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    positive_feedback_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    accuracy_measurement_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    correct_prediction_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
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

    tenant = relationship("Tenant")
