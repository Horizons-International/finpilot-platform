"""Async transactional outbox publishing for webhook events."""

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.webhook import Webhook, WebhookEvent
from app.utils.date_time import utc_now
from app.utils.enums import WebhookDeliveryStatus, WebhookStatus
from app.webhooks.events import SUPPORTED_WEBHOOK_EVENTS


async def enqueue_webhook_event_async(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    event_type: str,
    data: dict[str, Any],
) -> int:
    """Add matching webhook deliveries to the caller's current transaction.

    This function intentionally does not commit. The originating customer,
    compliance, or verification change and its outbox rows must succeed or roll
    back together. Payloads should contain identifiers and state, not customer PII.
    """
    if not isinstance(tenant_id, UUID):
        raise ValueError("A trusted tenant UUID is required for webhook events.")
    if event_type not in SUPPORTED_WEBHOOK_EVENTS:
        raise ValueError(f"Unsupported webhook event type: {event_type}")

    active_tenant_id = db.info.get("tenant_id")
    if active_tenant_id is not None and active_tenant_id != tenant_id:
        raise ValueError("Webhook event tenant does not match the active session.")
    db.info["tenant_id"] = tenant_id

    result = await db.scalars(
        select(Webhook).where(
            Webhook.tenant_id == tenant_id,
            Webhook.status == WebhookStatus.ACTIVE,
        )
    )
    subscriptions = result.all()
    now = utc_now()
    events: list[WebhookEvent] = []

    for webhook in subscriptions:
        if event_type not in webhook.event_types:
            continue
        event_id = uuid4()
        events.append(
            WebhookEvent(
                id=event_id,
                tenant_id=tenant_id,
                webhook_id=webhook.id,
                event_type=event_type,
                status=WebhookDeliveryStatus.PENDING,
                attempts=0,
                payload={
                    "id": str(event_id),
                    "type": event_type,
                    "created_at": now.isoformat(),
                    "data": data,
                },
                next_attempt_at=now,
            )
        )

    if events:
        db.add_all(events)
        await db.flush()
    return len(events)
