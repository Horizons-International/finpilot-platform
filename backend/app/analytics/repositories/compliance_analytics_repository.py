from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analytics.models.compliance_daily import ComplianceAnalyticsDaily
from app.analytics.tenant_context import resolve_tenant_id
from app.models.compliance_case import ComplianceCase
from app.models.verification_case import IdentityVerificationCase
from app.models.verification_review import VerificationReview
from app.utils.enums import ComplianceCaseStatus, ReviewDecision


class ComplianceAnalyticsRepository:
    """Tenant-scoped database operations for compliance analytics."""

    def __init__(self, db: Session, tenant_id: UUID) -> None:
        self.db = db
        self.tenant_id = resolve_tenant_id(db, tenant_id)

    @staticmethod
    def _start_datetime(value: date) -> datetime:
        return datetime.combine(value, time.min, tzinfo=timezone.utc)

    @staticmethod
    def _end_datetime_exclusive(value: date) -> datetime:
        return datetime.combine(
            value + timedelta(days=1), time.min, tzinfo=timezone.utc
        )

    def get_daily_snapshots(
        self, *, start_date: date, end_date: date
    ) -> list[ComplianceAnalyticsDaily]:
        statement = (
            select(ComplianceAnalyticsDaily)
            .where(
                ComplianceAnalyticsDaily.tenant_id == self.tenant_id,
                ComplianceAnalyticsDaily.snapshot_date >= start_date,
                ComplianceAnalyticsDaily.snapshot_date <= end_date,
            )
            .order_by(ComplianceAnalyticsDaily.snapshot_date)
        )
        return list(self.db.scalars(statement).all())

    def get_latest_snapshot(self, *, end_date: date) -> ComplianceAnalyticsDaily | None:
        statement = (
            select(ComplianceAnalyticsDaily)
            .where(
                ComplianceAnalyticsDaily.tenant_id == self.tenant_id,
                ComplianceAnalyticsDaily.snapshot_date <= end_date,
            )
            .order_by(ComplianceAnalyticsDaily.snapshot_date.desc())
            .limit(1)
        )
        return self.db.scalars(statement).first()

    def get_cases_created_by_day(
        self, *, start_date: date, end_date: date
    ) -> dict[date, int]:
        start_datetime = self._start_datetime(start_date)
        end_datetime = self._end_datetime_exclusive(end_date)
        day = func.date(func.timezone("UTC", ComplianceCase.created_at)).label(
            "snapshot_date"
        )
        statement = (
            select(day, func.count(ComplianceCase.id).label("case_count"))
            .where(
                ComplianceCase.tenant_id == self.tenant_id,
                ComplianceCase.created_at >= start_datetime,
                ComplianceCase.created_at < end_datetime,
            )
            .group_by(day)
            .order_by(day)
        )
        return {
            row._mapping["snapshot_date"]: int(row._mapping["case_count"] or 0)
            for row in self.db.execute(statement)
        }

    def get_cases_closed_by_day(
        self, *, start_date: date, end_date: date
    ) -> dict[date, tuple[int, float | None]]:
        start_datetime = self._start_datetime(start_date)
        end_datetime = self._end_datetime_exclusive(end_date)
        day = func.date(func.timezone("UTC", ComplianceCase.closed_at)).label(
            "snapshot_date"
        )
        average_seconds = func.avg(
            func.extract("epoch", ComplianceCase.closed_at - ComplianceCase.created_at)
        ).label("average_resolution_seconds")
        statement = (
            select(
                day, func.count(ComplianceCase.id).label("case_count"), average_seconds
            )
            .where(
                ComplianceCase.tenant_id == self.tenant_id,
                ComplianceCase.status == ComplianceCaseStatus.CLOSED,
                ComplianceCase.closed_at.is_not(None),
                ComplianceCase.closed_at >= start_datetime,
                ComplianceCase.closed_at < end_datetime,
            )
            .group_by(day)
            .order_by(day)
        )
        result: dict[date, tuple[int, float | None]] = {}
        for row in self.db.execute(statement):
            values = row._mapping
            avg = values["average_resolution_seconds"]
            result[values["snapshot_date"]] = (
                int(values["case_count"] or 0),
                float(avg) / 3600 if avg is not None else None,
            )
        return result

    def get_verification_rejection_reasons(
        self, *, start_date: date, end_date: date
    ) -> list[tuple[str, int]]:
        start_datetime = self._start_datetime(start_date)
        end_datetime = self._end_datetime_exclusive(end_date)
        reason = func.coalesce(
            func.nullif(func.trim(VerificationReview.notes), ""), "Unspecified"
        ).label("reason")
        statement = (
            select(reason, func.count(VerificationReview.id).label("count"))
            .join(
                IdentityVerificationCase,
                IdentityVerificationCase.id == VerificationReview.verification_case_id,
            )
            .where(
                VerificationReview.tenant_id == self.tenant_id,
                IdentityVerificationCase.tenant_id == self.tenant_id,
                VerificationReview.decision == ReviewDecision.REJECT,
                VerificationReview.created_at >= start_datetime,
                VerificationReview.created_at < end_datetime,
            )
            .group_by(reason)
            .order_by(func.count(VerificationReview.id).desc(), reason)
        )
        return [
            (str(row._mapping["reason"]), int(row._mapping["count"] or 0))
            for row in self.db.execute(statement)
        ]

    def get_case_resolution_summary(
        self, *, start_date: date, end_date: date
    ) -> tuple[int, float | None]:
        start_datetime = self._start_datetime(start_date)
        end_datetime = self._end_datetime_exclusive(end_date)
        average_seconds = func.avg(
            func.extract("epoch", ComplianceCase.closed_at - ComplianceCase.created_at)
        ).label("average_resolution_seconds")
        statement = select(
            func.count(ComplianceCase.id).label("closed_count"), average_seconds
        ).where(
            ComplianceCase.tenant_id == self.tenant_id,
            ComplianceCase.status == ComplianceCaseStatus.CLOSED,
            ComplianceCase.closed_at.is_not(None),
            ComplianceCase.closed_at >= start_datetime,
            ComplianceCase.closed_at < end_datetime,
        )
        row = self.db.execute(statement).one()
        avg = row._mapping["average_resolution_seconds"]
        return int(row._mapping["closed_count"] or 0), (
            float(avg) / 3600 if avg is not None else None
        )
