"""Unit tests for async transactional webhook outbox publishing."""

import asyncio
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.webhook import WebhookEvent
from app.utils.enums import WebhookDeliveryStatus
from app.webhooks.async_events import enqueue_webhook_event_async


class FakeScalarResult:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def all(self) -> list[object]:
        return self._rows


def _fake_session(tenant_id, subscriptions):
    return SimpleNamespace(
        info={"tenant_id": tenant_id},
        scalars=AsyncMock(return_value=FakeScalarResult(subscriptions)),
        add_all=Mock(),
        flush=AsyncMock(),
        commit=AsyncMock(),
    )


def test_async_webhook_publisher_adds_only_matching_active_subscriptions() -> None:
    async def run() -> None:
        tenant_id = uuid4()
        matching = SimpleNamespace(
            id=uuid4(), event_types=["customer.created", "case.closed"]
        )
        not_matching = SimpleNamespace(id=uuid4(), event_types=["case.closed"])
        db = _fake_session(tenant_id, [matching, not_matching])
        payload = {"customer_id": str(uuid4()), "status": "NEW"}

        count = await enqueue_webhook_event_async(
            cast(AsyncSession, db),
            tenant_id=tenant_id,
            event_type="customer.created",
            data=payload,
        )

        assert count == 1
        db.scalars.assert_awaited_once()
        db.add_all.assert_called_once()
        db.flush.assert_awaited_once()
        db.commit.assert_not_awaited()

        events = db.add_all.call_args.args[0]
        assert len(events) == 1
        event = events[0]
        assert isinstance(event, WebhookEvent)
        assert event.tenant_id == tenant_id
        assert event.webhook_id == matching.id
        assert event.event_type == "customer.created"
        assert event.status == WebhookDeliveryStatus.PENDING
        assert event.attempts == 0
        assert event.payload["type"] == "customer.created"
        assert event.payload["data"] == payload
        assert event.next_attempt_at is not None

    asyncio.run(run())


def test_async_webhook_publisher_rejects_unsupported_event() -> None:
    async def run() -> None:
        tenant_id = uuid4()
        db = _fake_session(tenant_id, [])
        with pytest.raises(ValueError, match="Unsupported webhook event type"):
            await enqueue_webhook_event_async(
                cast(AsyncSession, db),
                tenant_id=tenant_id,
                event_type="customer.deleted",
                data={},
            )
        db.scalars.assert_not_awaited()
        db.add_all.assert_not_called()
        db.flush.assert_not_awaited()

    asyncio.run(run())


def test_async_webhook_publisher_rejects_cross_tenant_session() -> None:
    async def run() -> None:
        tenant_id = uuid4()
        other_tenant_id = uuid4()
        db = _fake_session(other_tenant_id, [])
        with pytest.raises(ValueError, match="does not match the active session"):
            await enqueue_webhook_event_async(
                cast(AsyncSession, db),
                tenant_id=tenant_id,
                event_type="customer.created",
                data={},
            )
        db.scalars.assert_not_awaited()
        db.add_all.assert_not_called()
        db.flush.assert_not_awaited()

    asyncio.run(run())
