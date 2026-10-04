from datetime import date, datetime

from sqlalchemy import Date, DateTime, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ComplianceAnalyticsMonthly(Base):
    __tablename__ = "analytics_compliance_monthly"

    month_start: Mapped[date] = mapped_column(
        Date,
        primary_key=True,
    )

    # Number of compliance cases at the end of the calendar month.
    ending_total_cases: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Number of compliance cases created during the calendar month.
    cases_created_during_month: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Open compliance cases at the end of the calendar month.
    ending_open_cases: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Resolved compliance cases at the end of the calendar month.
    ending_resolved_cases: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Closed compliance cases at the end of the calendar month.
    ending_closed_cases: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # AML alerts that existed at the end of the calendar month.
    ending_total_alerts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # AML alerts created during the calendar month.
    alerts_created_during_month: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Risk distribution at the end of the calendar month.
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
