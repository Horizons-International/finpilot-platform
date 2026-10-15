"""Integration tests for tenant-scoped transaction anomaly detection."""

from datetime import timedelta
from uuid import UUID, uuid4

import pytest

from app.models.transaction_anomaly import (
    TransactionAnomaly,
    TransactionAnomalyActivity,
)
from app.utils.date_time import utc_now
from app.utils.enums import UserRole
from tests.helpers import authenticate_client, create_customer_with_data


@pytest.fixture
def cleanup_transaction_anomaly_data(db_session):
    initial_anomaly_ids = {
        anomaly_id for (anomaly_id,) in db_session.query(TransactionAnomaly.id).all()
    }
    initial_activity_ids = {
        activity_id
        for (activity_id,) in db_session.query(TransactionAnomalyActivity.id).all()
    }
    yield
    db_session.query(TransactionAnomaly).filter(
        ~TransactionAnomaly.id.in_(initial_anomaly_ids)
    ).delete(synchronize_session=False)
    db_session.query(TransactionAnomalyActivity).filter(
        ~TransactionAnomalyActivity.id.in_(initial_activity_ids)
    ).delete(synchronize_session=False)
    db_session.commit()


def _observation(transaction_id, amount, occurred_at, **overrides):
    data = {
        "transaction_id": str(transaction_id),
        "amount": amount,
        "currency": "GBP",
        "destination_country": "GB",
        "beneficiary_id": "known-beneficiary",
        "transaction_type": "TRANSFER",
        "occurred_at": occurred_at.isoformat(),
    }
    data.update(overrides)
    return data


def test_anomaly_analysis_detects_and_persists_deviations(
    client,
    create_test_user,
    cleanup_test_customers,
    cleanup_transaction_anomaly_data,
    db_session,
):
    admin = create_test_user(
        email=f"anomaly-admin-{uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )
    authenticate_client(client, admin)
    customer_response = create_customer_with_data(
        client,
        email=f"anomaly-customer-{uuid4()}@example.com",
        country_of_residence="GB",
    )
    assert customer_response.status_code == 201, customer_response.text
    customer_id = UUID(customer_response.json()["data"]["id"])

    now = utc_now()
    historical = [_observation(uuid4(), "500.00", now - timedelta(days=30))]
    current = [
        _observation(
            uuid4(),
            "2000.00",
            now - timedelta(minutes=10 - index),
            destination_country="US",
            beneficiary_id=f"new-beneficiary-{index}",
        )
        for index in range(10)
    ]

    response = client.post(
        "/api/v1/transaction-anomalies/analyze",
        json={
            "customer_id": str(customer_id),
            "historical_transactions": historical,
            "transactions": current,
        },
    )
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["transactions_analyzed"] == 10
    assert data["anomaly_count"] > 0

    anomaly_types = {row["anomaly_type"] for row in data["anomalies"]}
    assert "TRANSACTION_VOLUME_SPIKE" in anomaly_types
    assert "UNUSUAL_TRANSACTION_FREQUENCY" in anomaly_types
    assert "UNUSUAL_TRANSACTION_AMOUNT" in anomaly_types
    assert "NEW_DESTINATION_COUNTRY" in anomaly_types
    assert "NEW_BENEFICIARY" in anomaly_types
    assert any(row["risk_score"] >= 70 for row in data["anomalies"])

    history_response = client.get(
        "/api/v1/transaction-anomalies",
        params={"customer_id": str(customer_id)},
    )
    assert history_response.status_code == 200, history_response.text
    assert len(history_response.json()["data"]) == data["anomaly_count"]

    db_session.info["tenant_id"] = admin.tenant_id
    stored_activity = (
        db_session.query(TransactionAnomalyActivity)
        .filter(TransactionAnomalyActivity.customer_id == customer_id)
        .count()
    )
    assert stored_activity == 11  # one history row plus ten current transactions


def test_anomaly_analysis_rejects_duplicate_transaction_ids(
    client,
    create_test_user,
    cleanup_test_customers,
    cleanup_transaction_anomaly_data,
):
    admin = create_test_user(
        email=f"anomaly-duplicate-{uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )
    authenticate_client(client, admin)
    customer_response = create_customer_with_data(
        client, email=f"anomaly-duplicate-customer-{uuid4()}@example.com"
    )
    assert customer_response.status_code == 201, customer_response.text
    customer_id = customer_response.json()["data"]["id"]
    transaction = _observation(uuid4(), "100.00", utc_now())
    payload = {"customer_id": customer_id, "transactions": [transaction]}

    first = client.post("/api/v1/transaction-anomalies/analyze", json=payload)
    assert first.status_code == 201, first.text
    second = client.post("/api/v1/transaction-anomalies/analyze", json=payload)
    assert second.status_code == 409, second.text


def test_anomaly_history_is_tenant_scoped(
    client,
    create_test_user,
    create_test_tenant,
    cleanup_test_customers,
    cleanup_transaction_anomaly_data,
):
    first_tenant_admin = create_test_user(
        email=f"anomaly-tenant-a-{uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )
    second_tenant = create_test_tenant()
    second_tenant_admin = create_test_user(
        email=f"anomaly-tenant-b-{uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
        tenant_id=second_tenant.id,
    )

    authenticate_client(client, first_tenant_admin)
    customer_response = create_customer_with_data(
        client, email=f"anomaly-tenant-customer-{uuid4()}@example.com"
    )
    assert customer_response.status_code == 201, customer_response.text
    customer_id = customer_response.json()["data"]["id"]
    now = utc_now()
    payload = {
        "customer_id": customer_id,
        "historical_transactions": [
            _observation(uuid4(), "50.00", now - timedelta(days=5))
        ],
        "transactions": [
            _observation(
                uuid4(),
                "500.00",
                now,
                destination_country="US",
                beneficiary_id="new-payee",
            )
        ],
    }
    created = client.post("/api/v1/transaction-anomalies/analyze", json=payload)
    assert created.status_code == 201, created.text
    anomaly_id = created.json()["data"]["anomalies"][0]["id"]

    authenticate_client(client, second_tenant_admin)
    cross_tenant = client.get(f"/api/v1/transaction-anomalies/{anomaly_id}")
    assert cross_tenant.status_code == 404
