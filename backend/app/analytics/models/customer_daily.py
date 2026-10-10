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


class CustomerAnalyticsDaily(Base):
    __tablename__ = "analytics_customer_daily"

    __table_args__ = (
        Index(
            "uq_analytics_customer_daily_tenant_snapshot_date",
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
