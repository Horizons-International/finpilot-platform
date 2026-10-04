from datetime import date, datetime

from sqlalchemy import Date, DateTime, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ComplianceAnalyticsDaily(Base):
    __tablename__ = "analytics_compliance_daily"

    snapshot_date: Mapped[date] = mapped_column(
        Date,
        primary_key=True,
    )

    total_cases: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    open_cases: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    resolved_cases: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    closed_cases: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    total_alerts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    low_severity_alerts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    medium_severity_alerts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    high_severity_alerts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    critical_severity_alerts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    low_risk_customers: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    medium_risk_customers: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    high_risk_customers: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    critical_risk_customers: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
