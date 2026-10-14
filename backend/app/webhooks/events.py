"""Supported partner events and transactional outbox publishing."""

from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.webhook import Webhook, WebhookEvent
from app.utils.date_time import utc_now
from app.utils.enums import WebhookDeliveryStatus, WebhookStatus

SUPPORTED_WEBHOOK_EVENTS = (
    "customer.created",
    "customer.updated",
    "verification.completed",
    "verification.failed",
    "case.created",
    "case.closed",
)


def enqueue_webhook_event(
    db: Session,
    *,
    tenant_id: UUID,
    event_type: str,
    data: dict,
) -> int:
    """Write one outbox row for every active subscription in this tenant.

    Called inside the originating business transaction. If the business change
    rolls back, the corresponding webhook outbox rows roll back with it.
    Payloads intentionally contain identifiers and state, not customer PII.
    """
    if event_type not in SUPPORTED_WEBHOOK_EVENTS:
        raise ValueError(f"Unsupported webhook event type: {event_type}")

    active_tenant = db.info.get("tenant_id")
    if active_tenant is not None and active_tenant != tenant_id:
        raise ValueError("Webhook event tenant does not match the active session.")
    db.info["tenant_id"] = tenant_id

    subscriptions = db.scalars(
        select(Webhook).where(
            Webhook.tenant_id == tenant_id,
            Webhook.status == WebhookStatus.ACTIVE,
        )
    ).all()
    now = utc_now()
    count = 0
    for webhook in subscriptions:
        if event_type not in webhook.event_types:
            continue
        event_id = uuid4()
        payload = {
            "id": str(event_id),
            "type": event_type,
            "created_at": now.isoformat(),
            "data": data,
        }
        db.add(
            WebhookEvent(
                id=event_id,
                tenant_id=tenant_id,
                webhook_id=webhook.id,
                event_type=event_type,
                status=WebhookDeliveryStatus.PENDING,
                attempts=0,
                payload=payload,
                next_attempt_at=now,
            )
        )
        count += 1
    return count
