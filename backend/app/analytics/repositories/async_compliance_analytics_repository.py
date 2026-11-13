"""Async tenant-scoped compliance aggregate queries."""

from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.models.compliance_daily import ComplianceAnalyticsDaily
from app.models.compliance_case import ComplianceCase
from app.models.verification_case import IdentityVerificationCase
from app.models.verification_review import VerificationReview
from app.utils.enums import ComplianceCaseStatus, ReviewDecision


class AsyncComplianceAnalyticsRepository:
    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        active = db.info.get("tenant_id")
        if active is not None and active != tenant_id:
            raise ValueError(
                "Analytics repository tenant does not match session tenant."
            )
        db.info["tenant_id"] = tenant_id
        self.db = db
        self.tenant_id = tenant_id

    @staticmethod
    def _start(value: date) -> datetime:
        return datetime.combine(value, time.min, tzinfo=timezone.utc)

    @staticmethod
    def _end(value: date) -> datetime:
        return datetime.combine(
            value + timedelta(days=1), time.min, tzinfo=timezone.utc
        )

    async def get_daily_snapshots(
        self, *, start_date: date, end_date: date
    ) -> list[ComplianceAnalyticsDaily]:
        rows = await self.db.scalars(
            select(ComplianceAnalyticsDaily)
            .where(
                ComplianceAnalyticsDaily.tenant_id == self.tenant_id,
                ComplianceAnalyticsDaily.snapshot_date >= start_date,
                ComplianceAnalyticsDaily.snapshot_date <= end_date,
            )
            .order_by(ComplianceAnalyticsDaily.snapshot_date)
        )
        return list(rows.all())

    async def get_latest_snapshot(
        self, *, end_date: date
    ) -> ComplianceAnalyticsDaily | None:
        return await self.db.scalar(
            select(ComplianceAnalyticsDaily)
            .where(
                ComplianceAnalyticsDaily.tenant_id == self.tenant_id,
                ComplianceAnalyticsDaily.snapshot_date <= end_date,
            )
            .order_by(ComplianceAnalyticsDaily.snapshot_date.desc())
            .limit(1)
        )

    async def get_cases_created_by_day(
        self, *, start_date: date, end_date: date
    ) -> dict[date, int]:
        day = func.date(func.timezone("UTC", ComplianceCase.created_at)).label(
            "snapshot_date"
        )
        stmt = (
            select(day, func.count(ComplianceCase.id).label("case_count"))
            .where(
                ComplianceCase.tenant_id == self.tenant_id,
                ComplianceCase.created_at >= self._start(start_date),
                ComplianceCase.created_at < self._end(end_date),
            )
            .group_by(day)
            .order_by(day)
        )
        rows = (await self.db.execute(stmt)).all()
        return {row.snapshot_date: int(row.case_count or 0) for row in rows}

    async def get_cases_closed_by_day(
        self, *, start_date: date, end_date: date
    ) -> dict[date, tuple[int, float | None]]:
        day = func.date(func.timezone("UTC", ComplianceCase.closed_at)).label(
            "snapshot_date"
        )
        average = func.avg(
            func.extract("epoch", ComplianceCase.closed_at - ComplianceCase.created_at)
        ).label("average_resolution_seconds")
        stmt = (
            select(day, func.count(ComplianceCase.id).label("case_count"), average)
            .where(
                ComplianceCase.tenant_id == self.tenant_id,
                ComplianceCase.status == ComplianceCaseStatus.CLOSED,
                ComplianceCase.closed_at.is_not(None),
                ComplianceCase.closed_at >= self._start(start_date),
                ComplianceCase.closed_at < self._end(end_date),
            )
            .group_by(day)
            .order_by(day)
        )
        rows = (await self.db.execute(stmt)).all()
        return {
            row.snapshot_date: (
                int(row.case_count or 0),
                (
                    float(row.average_resolution_seconds) / 3600
                    if row.average_resolution_seconds is not None
                    else None
                ),
            )
            for row in rows
        }

    async def get_verification_rejection_reasons(
        self, *, start_date: date, end_date: date
    ) -> list[tuple[str, int]]:
        reason = func.coalesce(
            func.nullif(func.trim(VerificationReview.notes), ""), "Unspecified"
        ).label("reason")
        stmt = (
            select(reason, func.count(VerificationReview.id).label("count"))
            .join(
                IdentityVerificationCase,
                IdentityVerificationCase.id == VerificationReview.verification_case_id,
            )
            .where(
                VerificationReview.tenant_id == self.tenant_id,
                IdentityVerificationCase.tenant_id == self.tenant_id,
                VerificationReview.decision == ReviewDecision.REJECT,
                VerificationReview.created_at >= self._start(start_date),
                VerificationReview.created_at < self._end(end_date),
            )
            .group_by(reason)
            .order_by(func.count(VerificationReview.id).desc(), reason)
        )
        rows = (await self.db.execute(stmt)).all()
        return [(str(row.reason), int(row.count or 0)) for row in rows]

    async def get_case_resolution_summary(
        self, *, start_date: date, end_date: date
    ) -> tuple[int, float | None]:
        average = func.avg(
            func.extract("epoch", ComplianceCase.closed_at - ComplianceCase.created_at)
        ).label("average_resolution_seconds")
        stmt = select(
            func.count(ComplianceCase.id).label("closed_count"), average
        ).where(
            ComplianceCase.tenant_id == self.tenant_id,
            ComplianceCase.status == ComplianceCaseStatus.CLOSED,
            ComplianceCase.closed_at.is_not(None),
            ComplianceCase.closed_at >= self._start(start_date),
            ComplianceCase.closed_at < self._end(end_date),
        )
        row = (await self.db.execute(stmt)).one()
        average_seconds = row.average_resolution_seconds
        return int(row.closed_count or 0), (
            float(average_seconds) / 3600 if average_seconds is not None else None
        )
