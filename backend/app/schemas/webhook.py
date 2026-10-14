"""API schemas for webhook subscriptions and delivery history."""

import ipaddress
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.utils.enums import WebhookDeliveryStatus, WebhookStatus
from app.webhooks.events import SUPPORTED_WEBHOOK_EVENTS


class WebhookCreate(BaseModel):
    endpoint_url: str = Field(min_length=8, max_length=2048)
    event_types: list[str] = Field(min_length=1, max_length=20)

    @field_validator("endpoint_url")
    @classmethod
    def validate_endpoint(cls, value: str) -> str:
        value = value.strip()
        parts = urlsplit(value)
        try:
            _ = parts.port
        except ValueError as exc:
            raise ValueError("Webhook endpoint port is invalid.") from exc
        if parts.scheme.lower() != "https":
            raise ValueError("Webhook endpoints must use HTTPS.")
        if not parts.hostname or parts.username or parts.password or parts.fragment:
            raise ValueError("Webhook endpoint URL is invalid.")
        if parts.query:
            raise ValueError("Webhook endpoint URLs must not include query parameters.")
        host = parts.hostname.rstrip(".").lower()
        if host in {"localhost", "localhost.localdomain"} or host.endswith(
            (".localhost", ".local", ".internal")
        ):
            raise ValueError("Webhook endpoint must use a publicly addressable host.")
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if address is not None and not address.is_global:
            raise ValueError("Webhook endpoint must not use a private or reserved IP.")
        return value

    @field_validator("event_types")
    @classmethod
    def validate_events(cls, value: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(item.strip() for item in value))
        if not normalized or any(not item for item in normalized):
            raise ValueError("At least one event type is required.")
        unsupported = sorted(set(normalized) - set(SUPPORTED_WEBHOOK_EVENTS))
        if unsupported:
            unsupported_names = ", ".join(unsupported)
            raise ValueError(f"Unsupported webhook event type(s): {unsupported_names}")
        return normalized


class WebhookUpdate(BaseModel):
    endpoint_url: str | None = Field(default=None, min_length=8, max_length=2048)
    event_types: list[str] | None = Field(default=None, min_length=1, max_length=20)

    @field_validator("endpoint_url")
    @classmethod
    def validate_endpoint(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return WebhookCreate.validate_endpoint(value)

    @field_validator("event_types")
    @classmethod
    def validate_events(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return WebhookCreate.validate_events(value)

    @model_validator(mode="after")
    def require_update(self) -> "WebhookUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided.")
        return self


class WebhookStatusUpdate(BaseModel):
    status: WebhookStatus


class WebhookResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    endpoint_url: str
    event_types: list[str]
    status: WebhookStatus
    created_at: datetime
    updated_at: datetime
    last_delivery_at: datetime | None


class WebhookCreatedResponse(BaseModel):
    webhook: WebhookResponse
    signing_secret: str = Field(
        description="Shown only once when the webhook is created"
    )


class WebhookDeliveryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    webhook_id: UUID
    event_type: str
    status: WebhookDeliveryStatus
    attempts: int
    created_at: datetime
    next_attempt_at: datetime
    last_attempt_at: datetime | None
    delivered_at: datetime | None
    response_status: int | None
    last_error: str | None


class WebhookEventPayload(BaseModel):
    id: UUID
    type: str
    created_at: datetime
    data: dict[str, Any]
