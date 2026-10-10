import uuid
from datetime import date, datetime
from uuid import UUID

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ComplianceAnalyticsDaily(Base):
    __tablename__ = "analytics_compliance_daily"

    __table_args__ = (
        Index(
            "uq_analytics_compliance_daily_tenant_snapshot_date",
            "tenant_id",
            "snapshot_date",
            unique=True,
            postgresql_where=text("tenant_id IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    tenant_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True,
    )

    snapshot_date: Mapped[date] = mapped_column(
        Date,
    )

    # Number of compliance cases that existed
    # at the end of this snapshot day.
    ending_total_cases: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Number of compliance cases created during this calendar day.
    cases_created_during_day: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    # Number of open compliance cases at the end of this snapshot day.
    ending_open_cases: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Number of resolved compliance cases
    # at the end of this snapshot day.
    ending_resolved_cases: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Number of closed compliance cases at the end of this snapshot day.
    ending_closed_cases: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Number of AML alerts that existed at the end of this snapshot day.
    ending_total_alerts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Number of AML alerts created during this calendar day.
    alerts_created_during_day: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    # AML alerts by severity at the end of this snapshot day.
    ending_low_severity_alerts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    ending_medium_severity_alerts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    ending_high_severity_alerts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    ending_critical_severity_alerts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Customer risk distribution at the end of this snapshot day.
    ending_low_risk_customers: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    ending_medium_risk_customers: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    ending_high_risk_customers: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    ending_critical_risk_customers: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
