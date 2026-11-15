"""Additional integration coverage for the native-async anomaly API."""

from datetime import timedelta
from uuid import uuid4

import pytest

from app.models.transaction_anomaly import (
    TransactionAnomaly,
    TransactionAnomalyActivity,
)
from app.utils.date_time import utc_now
from app.utils.enums import UserRole
from tests.helpers import authenticate_client, create_customer_with_data


@pytest.fixture
def cleanup_async_transaction_anomaly_data(db_session):
    initial_anomaly_ids = {
        item_id for (item_id,) in db_session.query(TransactionAnomaly.id).all()
    }
    initial_activity_ids = {
        item_id for (item_id,) in db_session.query(TransactionAnomalyActivity.id).all()
    }
    yield
    db_session.query(TransactionAnomaly).filter(
        ~TransactionAnomaly.id.in_(initial_anomaly_ids)
    ).delete(synchronize_session=False)
    db_session.query(TransactionAnomalyActivity).filter(
        ~TransactionAnomalyActivity.id.in_(initial_activity_ids)
    ).delete(synchronize_session=False)
    db_session.commit()


def _transaction(transaction_id, occurred_at):
    return {
        "transaction_id": str(transaction_id),
        "amount": "250.00",
        "currency": "GBP",
        "destination_country": "GB",
        "beneficiary_id": "known-beneficiary",
        "transaction_type": "TRANSFER",
        "occurred_at": occurred_at.isoformat(),
    }


def test_async_anomaly_analysis_rejects_customer_from_another_tenant(
    client,
    create_test_user,
    create_test_tenant,
    cleanup_test_customers,
):
    first_admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email=f"async-anomaly-owner-{uuid4()}@example.com",
    )
    authenticate_client(client, first_admin)
    customer_response = create_customer_with_data(
        client,
        email=f"async-anomaly-owned-customer-{uuid4()}@example.com",
    )
    assert customer_response.status_code == 201, customer_response.text
    customer_id = customer_response.json()["data"]["id"]

    second_tenant = create_test_tenant()
    second_admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email=f"async-anomaly-other-tenant-{uuid4()}@example.com",
        tenant_id=second_tenant.id,
    )
    authenticate_client(client, second_admin)

    response = client.post(
        "/api/v1/transaction-anomalies/analyze",
        json={
            "customer_id": customer_id,
            "transactions": [_transaction(uuid4(), utc_now())],
        },
    )
    assert response.status_code == 404, response.text


def test_async_anomaly_list_is_tenant_scoped(
    client,
    create_test_user,
    create_test_tenant,
    cleanup_test_customers,
    cleanup_async_transaction_anomaly_data,
):
    owner = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email=f"async-anomaly-list-owner-{uuid4()}@example.com",
    )
    authenticate_client(client, owner)
    customer_response = create_customer_with_data(
        client,
        email=f"async-anomaly-list-customer-{uuid4()}@example.com",
    )
    assert customer_response.status_code == 201, customer_response.text
    customer_id = customer_response.json()["data"]["id"]

    now = utc_now()
    response = client.post(
        "/api/v1/transaction-anomalies/analyze",
        json={
            "customer_id": customer_id,
            "historical_transactions": [
                _transaction(uuid4(), now - timedelta(days=10))
            ],
            "transactions": [
                {
                    **_transaction(uuid4(), now),
                    "amount": "5000.00",
                    "destination_country": "US",
                    "beneficiary_id": "new-beneficiary",
                }
            ],
        },
    )
    assert response.status_code == 201, response.text

    other_tenant = create_test_tenant()
    other_admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email=f"async-anomaly-list-other-{uuid4()}@example.com",
        tenant_id=other_tenant.id,
    )
    authenticate_client(client, other_admin)
    history = client.get(
        "/api/v1/transaction-anomalies",
        params={"customer_id": customer_id},
    )
    assert history.status_code == 200, history.text
    assert history.json()["data"] == []
