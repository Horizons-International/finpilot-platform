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

    total_customers: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    new_registrations: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    pending_verification: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    verified_customers: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    suspended_customers: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    rejected_customers: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
