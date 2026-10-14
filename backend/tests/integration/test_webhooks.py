"""Integration coverage for webhook subscription management and delivery retries."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.models.webhook import Webhook, WebhookEvent
from app.utils.date_time import utc_now
from app.utils.enums import (
    UserRole,
    WebhookDeliveryStatus,
    WebhookStatus,
)
from app.webhooks.dispatcher import process_delivery
from app.webhooks.events import enqueue_webhook_event
from app.webhooks.security import decrypt_secret, sign_payload, verify_signature


def authenticate_client(client: TestClient, user) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "Password123!"},
    )
    assert response.status_code == 200, response.text
    token = response.json()["data"]["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})


@pytest.fixture
def cleanup_webhooks(db_session):
    initial_webhook_ids = {item.id for item in db_session.query(Webhook).all()}
    initial_event_ids = {item.id for item in db_session.query(WebhookEvent).all()}
    yield
    db_session.rollback()
    for event in db_session.query(WebhookEvent).all():
        if event.id not in initial_event_ids:
            db_session.delete(event)
    db_session.flush()
    for webhook in db_session.query(Webhook).all():
        if webhook.id not in initial_webhook_ids:
            db_session.delete(webhook)
    db_session.commit()


def create_webhook(client: TestClient, endpoint: str, events: list[str]):
    return client.post(
        "/api/v1/webhooks",
        json={"endpoint_url": endpoint, "event_types": events},
    )


def test_admin_can_register_list_and_disable_webhook(
    client: TestClient,
    db_session,
    create_test_user,
    cleanup_webhooks,
):
    admin = create_test_user(
        UserRole.ADMINISTRATOR,
        "webhook-admin@example.com",
    )
    authenticate_client(client, admin)

    response = create_webhook(
        client,
        "https://partner.example.com/finpilot/events",
        ["customer.created", "case.closed"],
    )
    assert response.status_code == 201, response.text
    body = response.json()["data"]
    webhook_id = body["webhook"]["id"]
    signing_secret = body["signing_secret"]
    assert signing_secret.startswith("whsec_")
    assert body["webhook"]["event_types"] == ["customer.created", "case.closed"]
    assert "secret_key" not in body["webhook"]

    db_session.info["tenant_id"] = admin.tenant_id
    record = db_session.query(Webhook).filter(Webhook.id == webhook_id).one()
    assert record.secret_key != signing_secret
    assert decrypt_secret(record.secret_key) == signing_secret

    listed = client.get("/api/v1/webhooks")
    assert listed.status_code == 200, listed.text
    listed_item = next(
        item for item in listed.json()["data"] if item["id"] == webhook_id
    )
    assert "secret_key" not in listed_item
    assert "signing_secret" not in listed_item

    disabled = client.patch(
        f"/api/v1/webhooks/{webhook_id}/status",
        json={"status": "DISABLED"},
    )
    assert disabled.status_code == 200, disabled.text
    assert disabled.json()["data"]["status"] == WebhookStatus.DISABLED.value


def test_webhook_event_selection_creates_tenant_scoped_outbox_rows(
    client: TestClient,
    db_session,
    create_test_user,
    cleanup_webhooks,
):
    admin = create_test_user(
        UserRole.ADMINISTRATOR,
        "webhook-events-admin@example.com",
    )
    authenticate_client(client, admin)
    response = create_webhook(
        client,
        "https://partner.example.com/finpilot/customer-events",
        ["customer.created"],
    )
    assert response.status_code == 201, response.text
    webhook_id = response.json()["data"]["webhook"]["id"]

    db_session.info["tenant_id"] = admin.tenant_id
    queued = enqueue_webhook_event(
        db_session,
        tenant_id=admin.tenant_id,
        event_type="customer.created",
        data={"customer_id": "7d389f8e-f3f6-4bb7-9be5-93a54af56be1", "status": "new"},
    )
    not_subscribed = enqueue_webhook_event(
        db_session,
        tenant_id=admin.tenant_id,
        event_type="customer.updated",
        data={"customer_id": "7d389f8e-f3f6-4bb7-9be5-93a54af56be1"},
    )
    db_session.commit()

    assert queued == 1
    assert not_subscribed == 0
    records = (
        db_session.query(WebhookEvent)
        .filter(WebhookEvent.webhook_id == webhook_id)
        .all()
    )
    assert len(records) == 1
    assert records[0].event_type == "customer.created"
    assert records[0].status == WebhookDeliveryStatus.PENDING
    assert records[0].payload["type"] == "customer.created"


def test_delivery_retries_then_records_success(
    client: TestClient,
    db_session,
    create_test_user,
    cleanup_webhooks,
):
    admin = create_test_user(
        UserRole.ADMINISTRATOR,
        "webhook-retry-admin@example.com",
    )
    authenticate_client(client, admin)
    response = create_webhook(
        client,
        "https://partner.example.com/finpilot/retry",
        ["case.closed"],
    )
    assert response.status_code == 201, response.text
    webhook_id = response.json()["data"]["webhook"]["id"]

    db_session.info["tenant_id"] = admin.tenant_id
    enqueue_webhook_event(
        db_session,
        tenant_id=admin.tenant_id,
        event_type="case.closed",
        data={"case_id": "2d7ffddb-1c26-4a5d-ae4d-dd6ff62f54a"},
    )
    db_session.commit()
    event = (
        db_session.query(WebhookEvent)
        .filter(WebhookEvent.webhook_id == webhook_id)
        .one()
    )
    event_id = event.id

    def failed_sender(endpoint, secret, payload, delivery_id, event_type):
        assert verify_signature(secret, payload, "sha256=" + "0" * 64) is False
        return 503, "temporarily unavailable"

    assert not process_delivery(
        db_session,
        delivery_id=event_id,
        tenant_id=admin.tenant_id,
        sender=failed_sender,
    )
    db_session.refresh(event)
    assert event.status == WebhookDeliveryStatus.RETRYING
    assert event.attempts == 1
    assert event.last_error is not None

    event.next_attempt_at = utc_now() - timedelta(seconds=1)
    db_session.commit()

    captured = {}

    def successful_sender(endpoint, secret, payload, delivery_id, event_type):
        signature = sign_payload(secret, payload)
        captured["signature_valid"] = verify_signature(secret, payload, signature)
        return 204, ""

    assert process_delivery(
        db_session,
        delivery_id=event_id,
        tenant_id=admin.tenant_id,
        sender=successful_sender,
    )
    db_session.refresh(event)
    assert captured["signature_valid"] is True
    assert event.status == WebhookDeliveryStatus.DELIVERED
    assert event.attempts == 2
    assert event.delivered_at is not None

    history = client.get(f"/api/v1/webhooks/{webhook_id}/deliveries")
    assert history.status_code == 200, history.text
    assert history.json()["data"][0]["status"] == WebhookDeliveryStatus.DELIVERED.value


def test_webhook_rejects_insecure_or_unknown_subscriptions(
    client: TestClient,
    create_test_user,
):
    admin = create_test_user(
        UserRole.ADMINISTRATOR,
        "webhook-validation-admin@example.com",
    )
    authenticate_client(client, admin)

    insecure = create_webhook(
        client,
        "http://partner.example.com/events",
        ["customer.created"],
    )
    assert insecure.status_code == 422

    unsupported = create_webhook(
        client,
        "https://partner.example.com/events",
        ["customer.password_exported"],
    )
    assert unsupported.status_code == 422


def test_customer_creation_enqueues_a_webhook_delivery(
    client: TestClient,
    db_session,
    create_test_user,
    cleanup_webhooks,
    cleanup_test_customers,
):
    admin = create_test_user(
        UserRole.ADMINISTRATOR,
        "webhook-customer-hook-admin@example.com",
    )
    authenticate_client(client, admin)
    response = create_webhook(
        client,
        "https://partner.example.com/finpilot/customer-created",
        ["customer.created", "customer.updated"],
    )
    assert response.status_code == 201, response.text
    webhook_id = response.json()["data"]["webhook"]["id"]

    customer_response = client.post(
        "/api/v1/customers",
        json={
            "first_name": "Webhook",
            "last_name": "Customer",
            "email": "webhook-event-customer@example.com",
            "phone_number": "+249912345678",
        },
    )
    assert customer_response.status_code == 201, customer_response.text
    customer_id = customer_response.json()["data"]["id"]
    update_response = client.put(
        f"/api/v1/customers/{customer_id}",
        json={"first_name": "WebhookUpdated"},
    )
    assert update_response.status_code == 200, update_response.text

    db_session.info["tenant_id"] = admin.tenant_id
    events = (
        db_session.query(WebhookEvent)
        .filter(WebhookEvent.webhook_id == webhook_id)
        .all()
    )
    assert {item.event_type for item in events} == {
        "customer.created",
        "customer.updated",
    }
    created_event = next(
        item for item in events if item.event_type == "customer.created"
    )
    updated_event = next(
        item for item in events if item.event_type == "customer.updated"
    )
    assert created_event.payload["data"]["customer_id"] == customer_id
    assert updated_event.payload["data"]["customer_id"] == customer_id
    assert updated_event.payload["data"]["changed_fields"] == ["first_name"]


def test_webhook_cannot_be_accessed_by_another_tenant(
    client: TestClient,
    create_test_user,
    create_test_tenant,
    cleanup_webhooks,
):
    owner_admin = create_test_user(
        UserRole.ADMINISTRATOR,
        "webhook-owner-admin@example.com",
    )
    authenticate_client(client, owner_admin)
    create_response = create_webhook(
        client,
        "https://partner.example.com/finpilot/private-events",
        ["customer.created"],
    )
    assert create_response.status_code == 201, create_response.text
    webhook_id = create_response.json()["data"]["webhook"]["id"]

    other_tenant = create_test_tenant()
    other_admin = create_test_user(
        UserRole.ADMINISTRATOR,
        "webhook-other-tenant-admin@example.com",
        tenant_id=other_tenant.id,
    )
    authenticate_client(client, other_admin)

    response = client.get(f"/api/v1/webhooks/{webhook_id}")
    assert response.status_code == 404
