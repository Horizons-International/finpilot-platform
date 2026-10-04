from datetime import date, datetime

from sqlalchemy import Date, DateTime, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CustomerAnalyticsDaily(Base):
    __tablename__ = "analytics_customer_daily"

    snapshot_date: Mapped[date] = mapped_column(
        Date,
        primary_key=True,
    )

    # Number of customers that existed at the end of this snapshot day.
    ending_total_customers: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Number of customers registered during this calendar day.
    customers_registered_during_day: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Number of verification cases approved during this calendar day.
    verification_approvals_during_day: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    # Number of customers with PENDING_VERIFICATION status
    # at the end of this snapshot day.
    ending_pending_verification_customers: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Number of customers with VERIFIED status
    # at the end of this snapshot day.
    ending_verified_customers: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Number of customers with SUSPENDED status
    # at the end of this snapshot day.
    ending_suspended_customers: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Number of customers with REJECTED status
    # at the end of this snapshot day.
    ending_rejected_customers: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
