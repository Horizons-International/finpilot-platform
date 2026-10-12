from datetime import date, datetime
from uuid import UUID, uuid4

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


class CustomerAnalyticsMonthly(Base):
    __tablename__ = "analytics_customer_monthly"

    __table_args__ = (
        Index(
            "uq_analytics_customer_monthly_tenant_month_start",
            "tenant_id",
            "month_start",
            unique=True,
            postgresql_where=text("tenant_id IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    tenant_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True,
    )

    month_start: Mapped[date] = mapped_column(
        Date,
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
