"""Small deterministic helpers used by the FinPilot Locust scenarios."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


def parse_bool(value: str | None, *, default: bool = False) -> bool:
    """Parse a conventional environment-variable boolean."""
    if value is None:
        return default
    return value.strip().casefold() in {"1", "true", "yes", "y", "on"}


def parse_csv_ids(value: str | None) -> list[str]:
    """Split a comma-separated list of non-empty fixture IDs."""
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def extract_access_token(payload: Any) -> str | None:
    """Extract the access token from the FinPilot APIResponse login envelope."""
    if not isinstance(payload, dict):
        return None
    data = payload.get("data")
    if not isinstance(data, dict):
        return None
    token = data.get("access_token")
    return token if isinstance(token, str) and token else None


def build_risk_analysis_payload(customer_id: str) -> dict[str, Any]:
    """Build a valid, synthetic transaction-risk request for a test tenant."""
    return {
        "customer_id": customer_id,
        "transactions": [
            {
                "transaction_id": str(uuid4()),
                "amount": "125.50",
                "currency": "USD",
                "destination_country": "US",
                "transaction_type": "CARD_PURCHASE",
                "occurred_at": datetime.now(UTC).isoformat(),
            }
        ],
        "historical_transactions": [],
    }
