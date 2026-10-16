from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest

from app.services.entity_intelligence_service import EntityIntelligenceService


def _customer(customer_id, first_name):
    return SimpleNamespace(
        id=customer_id,
        first_name=first_name,
        middle_name=None,
        last_name="Customer",
        status=SimpleNamespace(value="ACTIVE"),
        country_of_residence="US",
        nationality="US",
    )


def _activity(customer_id, transaction_id, occurred_at):
    return SimpleNamespace(
        id=uuid4(),
        customer_id=customer_id,
        transaction_id=transaction_id,
        amount=Decimal("100.00"),
        currency="USD",
        beneficiary_id="beneficiary-123",
        destination_country="US",
        transaction_type="TRANSFER",
        occurred_at=occurred_at,
    )


def test_sync_identifies_recipient_shared_by_two_customers(monkeypatch) -> None:
    tenant_id = uuid4()
    customer_a = _customer(uuid4(), "Ada")
    customer_b = _customer(uuid4(), "Grace")
    now = datetime.now(timezone.utc)
    activity_a = _activity(customer_a.id, uuid4(), now)
    activity_b = _activity(customer_b.id, uuid4(), now)

    repository = Mock()
    repository.get_customer.return_value = customer_a
    repository.list_customer_activity.return_value = [activity_a]
    repository.list_customer_risk_transactions.return_value = []
    repository.find_activities_for_beneficiaries.return_value = [
        activity_a,
        activity_b,
    ]
    repository.get_customers.return_value = [customer_a, customer_b]
    repository.anomaly_scores_for_transactions.return_value = {}

    nodes = {}
    relationships = {}

    def upsert_node(**values):
        key = (values["entity_type"], values["entity_key"])
        if key not in nodes:
            nodes[key] = SimpleNamespace(
                id=uuid4(),
                risk_score=values.get("risk_score", 0),
                risk_level="LOW",
            )
        return nodes[key]

    def upsert_relationship(**values):
        key = (
            values["source_entity_id"],
            values["target_entity_id"],
            values["relationship_type"],
        )
        if key not in relationships:
            relationships[key] = SimpleNamespace(id=uuid4(), **values)
        else:
            for field, value in values.items():
                setattr(relationships[key], field, value)
        return relationships[key]

    repository.upsert_node.side_effect = upsert_node
    repository.upsert_relationship.side_effect = upsert_relationship
    monkeypatch.setattr(
        "app.services.entity_intelligence_service.EntityIntelligenceRepository",
        lambda db, tenant_id: repository,
    )
    db = Mock()
    db.info = {}

    service = EntityIntelligenceService(db, tenant_id=tenant_id)
    response = service.sync_customer_activity(customer_a.id)

    shared_edges = [
        values for key, values in relationships.items() if key[2] == "SHARES_RECIPIENT"
    ]
    assert len(shared_edges) == 2
    assert all(edge.risk_score == 50 for edge in shared_edges)
    assert all(edge.evidence["distinct_customer_count"] == 2 for edge in shared_edges)
    assert response.risk_relationships_identified == 2
    assert response.transactions_indexed == 1
    assert db.commit.called


def test_service_rejects_a_mismatched_session_tenant() -> None:
    db = Mock()
    db.info = {"tenant_id": uuid4()}

    with pytest.raises(ValueError, match="already bound to another tenant"):
        EntityIntelligenceService(db, tenant_id=uuid4())
