from datetime import date, datetime

from sqlalchemy import Date, DateTime, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class OperationsAnalyticsDaily(Base):
    __tablename__ = "analytics_operations_daily"

    snapshot_date: Mapped[date] = mapped_column(
        Date,
        primary_key=True,
    )

    total_tasks: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    open_tasks: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    completed_tasks: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    overdue_tasks: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    task_sla_within_sla: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    task_sla_approaching_deadline: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    task_sla_breached: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    task_sla_completed: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    total_workflows: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    active_workflows: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    completed_workflows: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    failed_workflows: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    workflow_sla_within_sla: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    workflow_sla_approaching_deadline: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    workflow_sla_breached: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    workflow_sla_completed: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
