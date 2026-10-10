import time
from collections.abc import Callable
from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session

import app.analytics.models  # noqa: F401
import app.models  # noqa: F401
from app.analytics.services.aggregation_service import (
    AnalyticsAggregationService,
)
from app.core.database import SessionLocal
from app.core.logger import get_logger, setup_logging
from app.models.tenant import Tenant
from app.utils.date_time import utc_now
from app.utils.enums import TenantStatus

DAILY_ADVISORY_LOCK_KEY = "finpilot_analytics_daily"
MONTHLY_ADVISORY_LOCK_KEY = "finpilot_analytics_monthly"

setup_logging()
logger = get_logger(__name__)


def _aggregate_for_each_active_tenant(
    db: Session,
    callback: Callable[[Session, UUID], None],
) -> None:
    tenant_ids = list(
        db.scalars(
            select(Tenant.id).where(
                Tenant.status == TenantStatus.ACTIVE,
            )
        ).all()
    )

    failed_tenants: list[UUID] = []

    for tenant_id in tenant_ids:
        # Apply tenant context for ORM queries using the tenant listener.
        db.info["tenant_id"] = tenant_id

        try:
            callback(db, tenant_id)
            db.commit()

            logger.info(
                "Analytics aggregation completed for tenant %s.",
                tenant_id,
            )

        except Exception:
            db.rollback()
            failed_tenants.append(tenant_id)

            logger.exception(
                "Analytics aggregation failed for tenant %s.",
                tenant_id,
            )

        finally:
            # Do not let one tenant's context leak into the next iteration.
            db.info.pop("tenant_id", None)

    if failed_tenants:
        raise RuntimeError(
            f"Analytics aggregation failed for {len(failed_tenants)} tenant(s)."
        )


def _run_locked_job(
    *,
    lock_key: str,
    job_name: str,
    callback: Callable[[Session], None],
) -> int:
    db = SessionLocal()

    try:
        lock_result = db.execute(
            text("SELECT pg_try_advisory_lock(hashtext(:lock_key))"),
            {
                "lock_key": lock_key,
            },
        ).scalar()

        if not lock_result:
            logger.debug(
                "%s job is already running",
                job_name,
            )
            return 0

        try:
            callback(db)

            logger.info(
                "%s aggregation completed successfully",
                job_name,
            )

            return 1

        except Exception:
            db.rollback()

            logger.exception(
                "%s aggregation failed",
                job_name,
            )

            return 0

        finally:
            db.execute(
                text("SELECT pg_advisory_unlock(hashtext(:lock_key))"),
                {
                    "lock_key": lock_key,
                },
            )

    finally:
        db.close()


def run_daily_aggregation_once(
    *,
    aggregation_date: date | None = None,
) -> int:
    target_date = (
        aggregation_date
        if aggregation_date is not None
        else utc_now().date() - timedelta(days=1)
    )

    def aggregate_for_tenant(
        db: Session,
        tenant_id: UUID,
    ) -> None:
        AnalyticsAggregationService(
            db,
            tenant_id=tenant_id,
        ).aggregate_daily(
            aggregation_date=target_date,
        )

    def callback(db: Session) -> None:
        _aggregate_for_each_active_tenant(
            db,
            aggregate_for_tenant,
        )

    return _run_locked_job(
        lock_key=DAILY_ADVISORY_LOCK_KEY,
        job_name="Daily analytics",
        callback=callback,
    )


def run_monthly_aggregation_once(
    *,
    month_start: date | None = None,
) -> int:
    def aggregate_for_tenant(
        db: Session,
        tenant_id: UUID,
    ) -> None:
        AnalyticsAggregationService(
            db,
            tenant_id=tenant_id,
        ).aggregate_monthly(
            month_start=month_start,
        )

    def callback(db: Session) -> None:
        _aggregate_for_each_active_tenant(
            db,
            aggregate_for_tenant,
        )

    return _run_locked_job(
        lock_key=MONTHLY_ADVISORY_LOCK_KEY,
        job_name="Monthly analytics",
        callback=callback,
    )


def run_analytics_aggregator() -> None:
    logger.info("Analytics aggregator started.")

    while True:
        today = utc_now().date()

        run_daily_aggregation_once(
            aggregation_date=today - timedelta(days=1),
        )

        if today.day == 1:
            run_monthly_aggregation_once()

        now = utc_now()

        next_day = (now + timedelta(days=1)).replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )

        sleep_seconds = max(
            1,
            int((next_day - now).total_seconds()),
        )

        time.sleep(sleep_seconds)


if __name__ == "__main__":
    run_analytics_aggregator()
