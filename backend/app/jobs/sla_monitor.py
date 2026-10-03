import time

from sqlalchemy import text

# Make sure all SQLAlchemy models are registered before the worker
# creates/uses a Session.
import app.models  # noqa: F401
from app.core.config import settings
from app.core.database import SessionLocal
from app.core.logger import get_logger, setup_logging
from app.services.sla_service import SLAService

SLA_ADVISORY_LOCK_KEY = "finpilot_sla_monitor"

setup_logging()
logger = get_logger(__name__)


def run_sla_monitor_once() -> int:
    db = SessionLocal()

    try:
        lock_result = db.execute(
            text("SELECT pg_try_advisory_lock(hashtext(:lock_key))"),
            {"lock_key": SLA_ADVISORY_LOCK_KEY},
        ).scalar()

        if not lock_result:
            logger.debug("Another SLA monitor instance is already running")
            return 0

        try:
            changed = SLAService(db).check_all()
            logger.info("SLA monitor check completed. Changed=%s", changed)
            return changed
        finally:
            db.execute(
                text("SELECT pg_advisory_unlock(hashtext(:lock_key))"),
                {"lock_key": SLA_ADVISORY_LOCK_KEY},
            )

    except Exception:
        logger.exception("SLA monitor check failed")
        return 0
    finally:
        db.close()


def run_sla_monitor() -> None:
    logger.info(
        "SLA monitor started. Interval=%ss.",
        settings.SLA_MONITOR_INTERVAL_SECONDS,
    )

    while True:
        run_sla_monitor_once()
        time.sleep(settings.SLA_MONITOR_INTERVAL_SECONDS)


if __name__ == "__main__":
    run_sla_monitor()
