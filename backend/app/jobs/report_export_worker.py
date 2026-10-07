import time

from sqlalchemy import text

import app.models  # noqa: F401
from app.core.config import settings
from app.core.database import SessionLocal
from app.core.logger import get_logger, setup_logging
from app.repositories.report_export_repository import (
    ReportExportRepository,
)
from app.services.report_export_service import ReportExportService
from app.storages.local_storage import LocalStorage

REPORT_EXPORT_ADVISORY_LOCK_KEY = "finpilot_report_export_worker"

setup_logging()
logger = get_logger(__name__)


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

        try:
            repository = ReportExportRepository(db)

            report_export = repository.claim_next_requested()

            if report_export is None:
                return 0

            service = ReportExportService(
                db=db,
                storage=LocalStorage(
                    settings.STORAGE_PATH,
                ),
            )

            logger.info(
                "Processing report export %s.",
                report_export.id,
            )

            service.process_export(
                export_id=report_export.id,
            )

            logger.info(
                "Report export %s processed successfully.",
                report_export.id,
            )

            return 1

        finally:
            db.execute(
                text("SELECT pg_advisory_unlock(hashtext(:lock_key))"),
                {
                    "lock_key": REPORT_EXPORT_ADVISORY_LOCK_KEY,
                },
            )

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

        time.sleep(
            settings.REPORT_EXPORT_INTERVAL_SECONDS,
        )


if __name__ == "__main__":
    run_report_export_worker()
