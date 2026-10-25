import hashlib
import hmac
import json
import logging
import os
from typing import Any

from fastapi import FastAPI, HTTPException, Request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("finpilot.webhook_receiver")

app = FastAPI(title="FinPilot Test Webhook Receiver")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/webhook")
async def receive_webhook(request: Request) -> dict[str, Any]:
    # Set this environment variable to the signing secret returned
    # when you register the webhook in FinPilot.
    secret = os.environ.get("FINPILOT_WEBHOOK_SIGNING_SECRET", "")
    if not secret:
        raise HTTPException(
            status_code=503,
            detail="Webhook signing secret has not been configured.",
        )

    signature = request.headers.get("X-FinPilot-Signature", "")
    raw_body = await request.body()

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=400,
            detail="Request body must contain valid JSON.",
        ) from exc

    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=400,
            detail="Expected a JSON object.",
        )

    # FinPilot signs canonical JSON using HMAC-SHA256.
    canonical_body = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")

    expected_signature = (
        "sha256="
        + hmac.new(
            secret.encode("utf-8"),
            canonical_body,
            hashlib.sha256,
        ).hexdigest()
    )

    if not hmac.compare_digest(signature, expected_signature):
        raise HTTPException(
            status_code=401,
            detail="Invalid FinPilot webhook signature.",
        )

    event_type = request.headers.get(
        "X-FinPilot-Event",
        str(payload.get("type", "unknown")),
    )
    delivery_id = request.headers.get("X-FinPilot-Delivery", "unknown")
    event_id = payload.get("id", "unknown")

    # Log identifiers and event type, not the signing secret or full payload.
    logger.info(
        "Verified FinPilot webhook: type=%s event_id=%s delivery_id=%s",
        event_type,
        event_id,
        delivery_id,
    )

    # A 200 response tells FinPilot that delivery succeeded.
    return {
        "received": True,
        "event_type": event_type,
        "event_id": event_id,
    }
