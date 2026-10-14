"""Outbound webhook delivery, request signing, and retry scheduling."""

from __future__ import annotations

import ipaddress
import logging
import re
import socket
from collections.abc import Callable
from datetime import timedelta
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.webhook import Webhook, WebhookEvent
from app.utils.date_time import utc_now
from app.utils.enums import WebhookDeliveryStatus, WebhookStatus
from app.webhooks.security import canonical_json, decrypt_secret, sign_payload

logger = logging.getLogger(__name__)
_SECRET_RE = re.compile(
    r"(?i)(api[_ -]?key|access[_ -]?token|client[_ -]?secret|password|"
    r"secret|authorization)\s*([:=])\s*[^\s,;]+"
)
Sender = Callable[[str, str, dict, UUID, str], tuple[int, str]]


def _sanitize_message(message: str, secret: str | None = None) -> str:
    if secret:
        message = message.replace(secret, "[REDACTED]")
    return _SECRET_RE.sub(r"\1\2[REDACTED]", message)[:1000]


def _assert_public_destination(endpoint_url: str) -> None:
    """Reject obvious SSRF targets before making an outbound request.

    Production deployments should additionally enforce outbound network policy
    at the container/host firewall. DNS checks here reduce common SSRF risks but
    cannot alone prevent DNS rebinding between validation and connection.
    """
    parts = urlsplit(endpoint_url)
    if (
        parts.scheme != "https"
        or not parts.hostname
        or parts.username
        or parts.password
        or parts.query
        or parts.fragment
    ):
        raise ValueError("Webhook endpoint must be a valid HTTPS URL.")
    hostname = parts.hostname.rstrip(".").lower()
    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(
        (".localhost", ".local", ".internal")
    ):
        raise ValueError("Webhook endpoint resolves to a non-public destination.")
    try:
        addresses = [ipaddress.ip_address(hostname)]
    except ValueError:
        try:
            records = socket.getaddrinfo(
                hostname, parts.port or 443, type=socket.SOCK_STREAM
            )
        except OSError as exc:
            raise ConnectionError("Webhook hostname could not be resolved.") from exc
        addresses = [ipaddress.ip_address(record[4][0]) for record in records]
    if not addresses or any(not address.is_global for address in addresses):
        raise ValueError("Webhook endpoint resolves to a non-public destination.")


def _send_http(
    endpoint_url: str,
    secret: str,
    payload: dict,
    delivery_id: UUID,
    event_type: str,
) -> tuple[int, str]:
    _assert_public_destination(endpoint_url)
    signature = sign_payload(secret, payload)
    with httpx.Client(
        timeout=settings.WEBHOOK_DELIVERY_TIMEOUT_SECONDS,
        follow_redirects=False,
    ) as client:
        response = client.post(
            endpoint_url,
            content=canonical_json(payload),
            headers={
                "Content-Type": "application/json",
                "User-Agent": "FinPilot-Webhooks/1.0",
                "X-FinPilot-Event": event_type,
                "X-FinPilot-Delivery": str(delivery_id),
                "X-FinPilot-Signature": signature,
            },
        )
    return response.status_code, ""


def process_delivery(
    db: Session,
    *,
    delivery_id: UUID,
    tenant_id: UUID,
    sender: Sender | None = None,
) -> bool:
    """Attempt one due delivery. ``sender`` is injectable for deterministic tests."""
    now = utc_now()
    db.info["tenant_id"] = tenant_id
    event = db.scalar(
        select(WebhookEvent)
        .where(
            WebhookEvent.id == delivery_id,
            WebhookEvent.tenant_id == tenant_id,
        )
        .with_for_update()
    )
    if event is None:
        db.rollback()
        return False
    if event.status == WebhookDeliveryStatus.DELIVERING:
        stale_before = now - timedelta(
            seconds=settings.WEBHOOK_DELIVERY_TIMEOUT_SECONDS * 2
        )
        if event.last_attempt_at is not None and event.last_attempt_at > stale_before:
            db.rollback()
            return False
    elif (
        event.status
        not in {
            WebhookDeliveryStatus.PENDING,
            WebhookDeliveryStatus.RETRYING,
        }
        or event.next_attempt_at > now
    ):
        db.rollback()
        return False

    webhook = db.scalar(
        select(Webhook).where(
            Webhook.id == event.webhook_id,
            Webhook.tenant_id == tenant_id,
        )
    )
    if webhook is None:
        event.status = WebhookDeliveryStatus.FAILED
        event.last_error = "Webhook no longer exists."
        db.commit()
        return False
    if webhook.status != WebhookStatus.ACTIVE:
        # Preserve queued events while an administrator has intentionally
        # disabled the endpoint. Re-enable it to resume delivery.
        event.status = (
            WebhookDeliveryStatus.RETRYING
            if event.attempts > 0
            else WebhookDeliveryStatus.PENDING
        )
        event.next_attempt_at = now + timedelta(
            seconds=max(settings.WEBHOOK_DELIVERY_INTERVAL_SECONDS, 60)
        )
        event.last_error = "Delivery paused because the webhook is disabled."
        db.commit()
        return False

    endpoint_url = webhook.endpoint_url
    encrypted_secret = webhook.secret_key
    payload = event.payload
    event_type = event.event_type
    event.status = WebhookDeliveryStatus.DELIVERING
    event.attempts += 1
    event.last_attempt_at = now
    attempt_number = event.attempts
    db.commit()

    plain_secret: str | None = None
    response_status: int | None = None
    error: str | None = None
    try:
        plain_secret = decrypt_secret(encrypted_secret)
        response_status, _ = (sender or _send_http)(
            endpoint_url,
            plain_secret,
            payload,
            delivery_id,
            event_type,
        )
        if not 200 <= response_status < 300:
            error = f"Partner endpoint returned HTTP {response_status}."
    except Exception as exc:  # Record provider/network errors rather than propagating.
        error = f"{type(exc).__name__}: {_sanitize_message(str(exc), plain_secret)}"

    db.info["tenant_id"] = tenant_id
    current = db.scalar(
        select(WebhookEvent).where(
            WebhookEvent.id == delivery_id,
            WebhookEvent.tenant_id == tenant_id,
        )
    )
    if current is None:
        db.rollback()
        return False
    current.response_status = response_status
    webhook = db.scalar(
        select(Webhook).where(
            Webhook.id == current.webhook_id,
            Webhook.tenant_id == tenant_id,
        )
    )
    if error is None:
        current.status = WebhookDeliveryStatus.DELIVERED
        current.delivered_at = now
        if webhook is not None:
            webhook.last_delivery_at = now
        current.last_error = None
    else:
        current.last_error = _sanitize_message(error, plain_secret)
        if attempt_number >= settings.WEBHOOK_MAX_DELIVERY_ATTEMPTS:
            current.status = WebhookDeliveryStatus.FAILED
        else:
            current.status = WebhookDeliveryStatus.RETRYING
            delay = min(
                3600,
                settings.WEBHOOK_RETRY_BASE_SECONDS * (2 ** (attempt_number - 1)),
            )
            current.next_attempt_at = now + timedelta(seconds=delay)
    db.commit()
    if error:
        logger.warning(
            "Webhook delivery %s attempt %s failed: %s",
            delivery_id,
            attempt_number,
            current.last_error,
        )
        return False
    return True
