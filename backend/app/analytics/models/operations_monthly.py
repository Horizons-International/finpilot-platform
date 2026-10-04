from datetime import date, datetime

from sqlalchemy import Date, DateTime, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class OperationsAnalyticsMonthly(Base):
    __tablename__ = "analytics_operations_monthly"

    month_start: Mapped[date] = mapped_column(
        Date,
        primary_key=True,
    )

    # Task count at the end of the calendar month.
    ending_total_tasks: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Tasks created during the calendar month.
    tasks_created_during_month: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Tasks completed during the calendar month.
    tasks_completed_during_month: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Open tasks at the end of the calendar month.
    ending_open_tasks: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Overdue open tasks at the end of the calendar month.
    ending_overdue_tasks: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Tasks completed during the month within SLA.
    tasks_completed_within_sla_during_month: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Tasks completed during the month after their SLA deadline.
    tasks_completed_breached_sla_during_month: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Workflow executions at the end of the calendar month.
    ending_total_workflows: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Workflow executions started during the calendar month.
    workflows_started_during_month: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Workflow executions completed during the calendar month.
    workflows_completed_during_month: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Workflow executions that failed during the calendar month.
    workflows_failed_during_month: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Active workflow executions at the end of the calendar month.
    ending_active_workflows: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Workflows completed during the month within SLA.
    workflows_completed_within_sla_during_month: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Workflows completed during the month after their SLA deadline.
    workflows_completed_breached_sla_during_month: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
