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

    # Number of tasks that existed at the end of this snapshot day.
    ending_total_tasks: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Number of tasks created during this calendar day.
    tasks_created_during_day: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    # Number of tasks still open at the end of this snapshot day.
    ending_open_tasks: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Number of tasks that had reached COMPLETED status
    # by the end of this snapshot day.
    ending_total_completed_tasks: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Number of tasks completed during this calendar day.
    tasks_completed_during_day: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    # Number of open tasks that were overdue at the end of this snapshot day.
    ending_overdue_tasks: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Number of tasks classified as WITHIN_SLA
    # at the end of this snapshot day.
    ending_tasks_sla_within_target: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Number of tasks classified as APPROACHING_DEADLINE
    # at the end of this snapshot day.
    ending_tasks_sla_approaching_deadline: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Number of tasks classified as BREACHED
    # at the end of this snapshot day.
    ending_tasks_sla_breached: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Number of tasks classified as completed within SLA
    # at the end of this snapshot day.
    ending_tasks_sla_completed_on_time: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Number of tasks completed during this calendar day within SLA.
    tasks_completed_within_sla_during_day: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    # Number of tasks completed during this calendar day after their SLA deadline.
    tasks_completed_breached_sla_during_day: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    # Number of workflow executions that existed
    # at the end of this snapshot day.
    ending_total_workflows: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Number of workflow executions started during this calendar day.
    workflows_started_during_day: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    # Number of workflow executions still active
    # at the end of this snapshot day.
    ending_active_workflows: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Number of workflow executions that had reached COMPLETED status
    # by the end of this snapshot day.
    ending_total_completed_workflows: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Number of workflow executions completed during this calendar day.
    workflows_completed_during_day: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    # Number of workflow executions that had reached FAILED status
    # by the end of this snapshot day.
    ending_total_failed_workflows: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Number of workflow executions that failed during this calendar day.
    workflows_failed_during_day: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    # Number of workflows classified as WITHIN_SLA
    # at the end of this snapshot day.
    ending_workflows_sla_within_target: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Number of workflows classified as APPROACHING_DEADLINE
    # at the end of this snapshot day.
    ending_workflows_sla_approaching_deadline: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Number of workflows classified as BREACHED
    # at the end of this snapshot day.
    ending_workflows_sla_breached: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Number of workflows classified as completed within SLA
    # at the end of this snapshot day.
    ending_workflows_sla_completed_on_time: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Number of workflows completed during this calendar day within SLA.
    workflows_completed_within_sla_during_day: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    # Number of workflows completed during this calendar day after their SLA deadline.
    workflows_completed_breached_sla_during_day: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
