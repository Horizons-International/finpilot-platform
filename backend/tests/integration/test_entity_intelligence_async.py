"""Integration tests for the native-async entity-intelligence API."""

from uuid import uuid4

import pytest

from app.models.entity_intelligence import (
    EntityIntelligenceNode,
    EntityIntelligenceRelationship,
)
from app.models.transaction_anomaly import TransactionAnomalyActivity
from app.utils.date_time import utc_now
from app.utils.enums import UserRole
from tests.helpers import authenticate_client, create_customer_with_data


@pytest.fixture
def cleanup_async_entity_graph(db_session):
    existing_node_ids = {
        node_id for (node_id,) in db_session.query(EntityIntelligenceNode.id).all()
    }
    existing_relationship_ids = {
        relationship_id
        for (relationship_id,) in db_session.query(
            EntityIntelligenceRelationship.id
        ).all()
    }
    yield
    db_session.query(EntityIntelligenceRelationship).filter(
        ~EntityIntelligenceRelationship.id.in_(existing_relationship_ids)
    ).delete(synchronize_session=False)
    db_session.query(EntityIntelligenceNode).filter(
        ~EntityIntelligenceNode.id.in_(existing_node_ids)
    ).delete(synchronize_session=False)
    db_session.commit()


def _create_node(client, *, entity_type: str, entity_key: str, label: str) -> str:
    response = client.post(
        "/api/v1/entity-intelligence/entities",
        json={
            "entity_type": entity_type,
            "entity_key": entity_key,
            "label": label,
            "source_type": "integration_test",
            "attributes": {"test_marker": True},
        },
    )
    assert response.status_code == 201, response.text
    payload: object = response.json()
    assert isinstance(payload, dict), "Expected a JSON object response."

    data = payload.get("data")
    assert isinstance(data, dict), "Expected a data object in the response."

    node_id = data.get("id")
    assert isinstance(node_id, str), "Expected the entity ID to be a string."

    return node_id


def test_async_entity_and_relationship_endpoints_build_graph(
    client, create_test_user, cleanup_async_entity_graph
):
    admin = create_test_user(
        email=f"entity-async-admin-{uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )
    authenticate_client(client, admin)

    source_id = _create_node(
        client,
        entity_type="CUSTOMER_REFERENCE",
        entity_key=f"customer-ref-{uuid4()}",
        label="Customer reference",
    )
    target_id = _create_node(
        client,
        entity_type="ACCOUNT_REFERENCE",
        entity_key=f"account-ref-{uuid4()}",
        label="Account reference",
    )

    relation_response = client.post(
        "/api/v1/entity-intelligence/relationships",
        json={
            "source_entity_id": source_id,
            "target_entity_id": target_id,
            "relationship_type": "OWNS_ACCOUNT",
            "confidence": 0.95,
            "evidence": {"source": "verified_customer_record"},
        },
    )
    assert relation_response.status_code == 201, relation_response.text

    entity_response = client.get(f"/api/v1/entity-intelligence/entities/{source_id}")
    assert entity_response.status_code == 200, entity_response.text
    assert entity_response.json()["data"]["entity_type"] == "CUSTOMER_REFERENCE"

    graph_response = client.get(f"/api/v1/entity-intelligence/graph/{source_id}")
    assert graph_response.status_code == 200, graph_response.text
    graph = graph_response.json()["data"]
    assert len(graph["nodes"]) == 2
    assert len(graph["relationships"]) == 1
    assert graph["relationships"][0]["relationship_type"] == "OWNS_ACCOUNT"


def test_async_entity_endpoints_are_tenant_scoped(
    client, create_test_user, create_test_tenant, cleanup_async_entity_graph
):
    first_admin = create_test_user(
        email=f"entity-async-tenant-a-{uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )
    second_tenant = create_test_tenant()
    second_admin = create_test_user(
        email=f"entity-async-tenant-b-{uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
        tenant_id=second_tenant.id,
    )

    authenticate_client(client, first_admin)
    foreign_node_id = _create_node(
        client,
        entity_type="PRIVATE_REFERENCE",
        entity_key=f"private-{uuid4()}",
        label="Private tenant entity",
    )

    authenticate_client(client, second_admin)
    get_response = client.get(f"/api/v1/entity-intelligence/entities/{foreign_node_id}")
    assert get_response.status_code == 404

    own_node_id = _create_node(
        client,
        entity_type="PUBLIC_REFERENCE",
        entity_key=f"tenant-b-{uuid4()}",
        label="Tenant B entity",
    )
    relationship_response = client.post(
        "/api/v1/entity-intelligence/relationships",
        json={
            "source_entity_id": foreign_node_id,
            "target_entity_id": own_node_id,
            "relationship_type": "RELATED_TO",
            "confidence": 1.0,
        },
    )
    assert relationship_response.status_code == 404


def test_async_graph_sync_detects_shared_recipient_across_customers(
    client,
    db_session,
    create_test_user,
    cleanup_test_customers,
    cleanup_async_entity_graph,
):
    admin = create_test_user(
        email=f"entity-sync-admin-{uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )
    authenticate_client(client, admin)

    first_customer_response = create_customer_with_data(
        client,
        email=f"entity-sync-first-{uuid4()}@example.com",
        country_of_residence="GB",
    )
    second_customer_response = create_customer_with_data(
        client,
        email=f"entity-sync-second-{uuid4()}@example.com",
        country_of_residence="GB",
    )
    assert first_customer_response.status_code == 201, first_customer_response.text
    assert second_customer_response.status_code == 201, second_customer_response.text
    first_customer_id = first_customer_response.json()["data"]["id"]
    second_customer_id = second_customer_response.json()["data"]["id"]

    shared_beneficiary = f"shared-beneficiary-{uuid4()}"
    now = utc_now()
    db_session.add_all(
        [
            TransactionAnomalyActivity(
                tenant_id=admin.tenant_id,
                customer_id=first_customer_id,
                transaction_id=uuid4(),
                amount="125.00",
                currency="GBP",
                destination_country="GB",
                beneficiary_id=shared_beneficiary,
                transaction_type="TRANSFER",
                occurred_at=now,
            ),
            TransactionAnomalyActivity(
                tenant_id=admin.tenant_id,
                customer_id=second_customer_id,
                transaction_id=uuid4(),
                amount="225.00",
                currency="GBP",
                destination_country="GB",
                beneficiary_id=shared_beneficiary,
                transaction_type="TRANSFER",
                occurred_at=now,
            ),
        ]
    )
    db_session.commit()

    sync_response = client.post(
        f"/api/v1/entity-intelligence/customers/{first_customer_id}/sync"
    )
    assert sync_response.status_code == 200, sync_response.text
    assert sync_response.json()["data"]["risk_relationships_identified"] == 2

    risk_response = client.get(
        "/api/v1/entity-intelligence/risk-relationships",
        params={"min_risk_score": 40},
    )
    assert risk_response.status_code == 200, risk_response.text
    assert any(
        "SHARED_RECIPIENT_ACROSS_CUSTOMERS" in item["risk_indicators"]
        for item in risk_response.json()["data"]
    )
