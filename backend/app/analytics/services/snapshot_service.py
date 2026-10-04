from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.analytics.models.compliance_daily import ComplianceAnalyticsDaily
from app.analytics.models.customer_daily import CustomerAnalyticsDaily
from app.analytics.models.operations_daily import OperationsAnalyticsDaily
from app.analytics.repositories.snapshot_repository import (
    AnalyticsSnapshotRepository,
)
from app.utils.date_time import utc_now


class AnalyticsSnapshotService:
    """Coordinates creation of daily analytics snapshots."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = AnalyticsSnapshotRepository(db)

    @staticmethod
    def _normalize_as_of(
        as_of: datetime | None,
    ) -> datetime:
        timestamp = as_of or utc_now()

        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(
                tzinfo=timezone.utc,
            )

        return timestamp.astimezone(timezone.utc)

    def capture_snapshot(
        self,
        *,
        as_of: datetime | None = None,
        commit: bool = True,
    ) -> tuple[
        CustomerAnalyticsDaily,
        ComplianceAnalyticsDaily,
        OperationsAnalyticsDaily,
    ]:
        captured_at = self._normalize_as_of(as_of)
        snapshot_date = captured_at.date()

        customer_metrics = self.repository.collect_customer_metrics(
            as_of=captured_at,
        )

        compliance_metrics = self.repository.collect_compliance_metrics(
            as_of=captured_at,
        )

        operations_metrics = self.repository.collect_operations_metrics(
            as_of=captured_at,
        )

        customer_snapshot = self.repository.save_customer_snapshot(
            snapshot_date=snapshot_date,
            captured_at=captured_at,
            metrics=customer_metrics,
        )

        compliance_snapshot = self.repository.save_compliance_snapshot(
            snapshot_date=snapshot_date,
            captured_at=captured_at,
            metrics=compliance_metrics,
        )

        operations_snapshot = self.repository.save_operations_snapshot(
            snapshot_date=snapshot_date,
            captured_at=captured_at,
            metrics=operations_metrics,
        )

        self.db.flush()

        if commit:
            self.db.commit()

            self.db.refresh(customer_snapshot)
            self.db.refresh(compliance_snapshot)
            self.db.refresh(operations_snapshot)

        return (
            customer_snapshot,
            compliance_snapshot,
            operations_snapshot,
        )
