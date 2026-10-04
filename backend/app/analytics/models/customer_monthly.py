from datetime import date, datetime

from sqlalchemy import Date, DateTime, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CustomerAnalyticsMonthly(Base):
    __tablename__ = "analytics_customer_monthly"

    month_start: Mapped[date] = mapped_column(
        Date,
        primary_key=True,
    )

    # Total number of customers at the end of the calendar month.
    ending_total_customers: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Number of customers registered during the calendar month.
    customers_registered_during_month: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Number of verification cases approved during the calendar month.
    verification_approvals_during_month: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Change in total customer count compared with the
    # last available snapshot before this month.
    customer_growth: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
