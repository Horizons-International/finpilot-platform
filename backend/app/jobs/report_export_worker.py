import time

from sqlalchemy import select, text

import app.models  # noqa: F401
from app.core.config import settings
from app.core.database import SessionLocal
from app.core.logger import get_logger, setup_logging
from app.models.report_export import ReportExport
from app.repositories.report_export_repository import (
    ReportExportRepository,
)
from app.services.report_export_service import ReportExportService
from app.storages.local_storage import LocalStorage
from app.utils.date_time import utc_now
from app.utils.enums import ReportExportStatus

REPORT_EXPORT_ADVISORY_LOCK_KEY = "finpilot_report_export_worker"
setup_logging()
logger = get_logger(__name__)


def _claim_next_export_for_any_tenant(
    db,
) -> tuple[ReportExport, ReportExportRepository] | None:
    """Claim one queued export globally, then bind the session to its tenant.

    The only unscoped read is the queue-discovery query, which fetches an ID and
    tenant ID under a row lock. It deliberately opts out of the tenant hook with
    a documented reason; the row is reloaded and mutated only after the session
    is bound to that row's tenant.
    """
    queued = db.execute(
        select(ReportExport.id, ReportExport.tenant_id)
        .where(ReportExport.status == ReportExportStatus.REQUESTED)
        .order_by(ReportExport.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
        .execution_options(
            skip_tenant_filter=True,
            tenant_scope_reason="report export worker discovers the next queue item",
        )
    ).first()

    if queued is None:
        return None

    export_id, tenant_id = queued
    db.info["tenant_id"] = tenant_id
    repository = ReportExportRepository(db, tenant_id=tenant_id)
    report_export = repository.get_by_id(export_id)
    if report_export is None:
        db.rollback()
        return None

    # The global SELECT holds the row lock. Update only after tenant binding.
    report_export.status = ReportExportStatus.PROCESSING
    report_export.started_at = utc_now()
    db.commit()
    db.refresh(report_export)
    return report_export, repository


def run_report_export_worker_once() -> int:
    db = SessionLocal()

    try:
        lock_result = db.execute(
            text("SELECT pg_try_advisory_lock(hashtext(:lock_key))"),
            {
                "lock_key": REPORT_EXPORT_ADVISORY_LOCK_KEY,
            },
        ).scalar()

        if not lock_result:
            logger.debug("Another report export worker instance is already running.")
            return 0

        claimed = _claim_next_export_for_any_tenant(db)
        if claimed is None:
            return 0

        report_export, _repository = claimed
        tenant_id = report_export.tenant_id

        try:
            service = ReportExportService(
                db=db,
                storage=LocalStorage(settings.STORAGE_PATH),
                tenant_id=tenant_id,
            )

            logger.info(
                "Processing report export %s for tenant %s.",
                report_export.id,
                tenant_id,
            )

            service.process_export(export_id=report_export.id)

            logger.info(
                "Report export %s processed successfully.",
                report_export.id,
            )
            return 1
        finally:
            # Do not reuse this session across tenant contexts.
            db.info.pop("tenant_id", None)
            db.info.pop("tenant_user_id", None)
            db.info.pop("tenant_user_email", None)
            db.info.pop("tenant_ip_address", None)
            db.info.pop("tenant_user_agent", None)

    except Exception:
        logger.exception("Report export worker failed.")
        return 0

    finally:
        db.close()


def run_report_export_worker() -> None:
    logger.info(
        "Report export worker started. Interval=%ss.",
        settings.REPORT_EXPORT_INTERVAL_SECONDS,
    )

    while True:
        run_report_export_worker_once()
        time.sleep(settings.REPORT_EXPORT_INTERVAL_SECONDS)


if __name__ == "__main__":
    run_report_export_worker()
