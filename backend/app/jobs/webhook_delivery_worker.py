"""Background worker for queued webhook deliveries."""

import time
from datetime import timedelta

from sqlalchemy import and_, or_, select

import app.models  # noqa: F401
from app.core.config import settings
from app.core.database import SessionLocal
from app.core.logger import get_logger, setup_logging
from app.core.tenant_filter import install_tenant_filter
from app.models.webhook import WebhookEvent
from app.utils.date_time import utc_now
from app.utils.enums import WebhookDeliveryStatus
from app.webhooks.dispatcher import process_delivery

setup_logging()
logger = get_logger(__name__)


def run_webhook_delivery_worker_once(batch_size: int = 25) -> int:
    """Process a batch of due events safely across tenant boundaries."""
    install_tenant_filter()
    db = SessionLocal()
    processed = 0
    try:
        now = utc_now()
        stale_before = now - timedelta(
            seconds=settings.WEBHOOK_DELIVERY_TIMEOUT_SECONDS * 2
        )
        candidates = db.execute(
            select(WebhookEvent.id, WebhookEvent.tenant_id)
            .where(
                or_(
                    and_(
                        WebhookEvent.status.in_(
                            (
                                WebhookDeliveryStatus.PENDING,
                                WebhookDeliveryStatus.RETRYING,
                            )
                        ),
                        WebhookEvent.next_attempt_at <= now,
                    ),
                    and_(
                        WebhookEvent.status == WebhookDeliveryStatus.DELIVERING,
                        or_(
                            WebhookEvent.last_attempt_at.is_(None),
                            WebhookEvent.last_attempt_at <= stale_before,
                        ),
                    ),
                )
            )
            .order_by(WebhookEvent.next_attempt_at, WebhookEvent.created_at)
            .limit(batch_size)
            .with_for_update(skip_locked=True)
            .execution_options(
                skip_tenant_filter=True,
                tenant_scope_reason=(
                    "webhook worker discovers due delivery IDs across tenants"
                ),
            )
        ).all()
        # Release the queue scan's row locks; process_delivery re-locks and
        # rechecks each row under its tenant context before claiming it.
        db.commit()
        for delivery_id, tenant_id in candidates:
            try:
                if process_delivery(
                    db,
                    delivery_id=delivery_id,
                    tenant_id=tenant_id,
                ):
                    processed += 1
            except Exception:
                db.rollback()
                logger.exception(
                    "Unexpected failure processing webhook %s", delivery_id
                )
        return processed
    except Exception:
        db.rollback()
        logger.exception("Webhook delivery worker batch failed")
        return processed
    finally:
        db.close()


def run_webhook_delivery_worker() -> None:
    logger.info(
        "Webhook delivery worker started. Interval=%ss.",
        settings.WEBHOOK_DELIVERY_INTERVAL_SECONDS,
    )
    while True:
        run_webhook_delivery_worker_once()
        time.sleep(settings.WEBHOOK_DELIVERY_INTERVAL_SECONDS)


if __name__ == "__main__":
    run_webhook_delivery_worker()
