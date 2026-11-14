"""Integration tests for tenant-local task-rule names and metric keys."""

from uuid import uuid4

from app.utils.enums import TaskAssignmentStrategy, UserRole
from tests.helpers import authenticate_client


def test_task_assignment_rule_name_can_be_reused_by_another_tenant(
    client,
    create_test_user,
    create_test_tenant,
    cleanup_task_assignment_rules,
):
    first_admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email=f"task-rule-unique-first-{uuid4()}@example.com",
    )
    second_tenant = create_test_tenant()
    second_admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email=f"task-rule-unique-second-{uuid4()}@example.com",
        tenant_id=second_tenant.id,
    )

    shared_name = f"Tenant-local assignment rule {uuid4()}"
    payload = {
        "name": shared_name,
        "description": "The same name is valid in different organizations.",
        "conditions": {"role": "Reviewer"},
        "strategy": TaskAssignmentStrategy.LEAST_LOADED.value,
        "priority": 10,
    }

    authenticate_client(client, first_admin)
    first_response = client.post("/api/v1/task-assignment-rules", json=payload)
    assert first_response.status_code == 200, first_response.text

    same_tenant_duplicate = client.post("/api/v1/task-assignment-rules", json=payload)
    assert same_tenant_duplicate.status_code == 400, same_tenant_duplicate.text

    authenticate_client(client, second_admin)
    second_response = client.post("/api/v1/task-assignment-rules", json=payload)
    assert second_response.status_code == 200, second_response.text
    assert second_response.json()["data"]["name"] == shared_name


def test_metric_key_can_be_reused_by_another_tenant(
    client,
    create_test_user,
    create_test_tenant,
    cleanup_metric_definitions,
):
    first_admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email=f"metric-unique-first-{uuid4()}@example.com",
    )
    second_tenant = create_test_tenant()
    second_admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email=f"metric-unique-second-{uuid4()}@example.com",
        tenant_id=second_tenant.id,
    )

    shared_key = f"tenant_local_metric_{uuid4().hex}"
    payload = {
        "key": shared_key,
        "name": "Tenant-local metric",
        "description": "The same key is valid in different organizations.",
        "category": "CUSTOMER",
        "value_type": "PERCENTAGE",
        "definition": {
            "type": "ratio",
            "numerator": "customer_registrations",
            "denominator": "customer_opening_base",
            "multiplier": 100,
            "precision": 2,
        },
        "status": "ACTIVE",
    }

    authenticate_client(client, first_admin)
    first_response = client.post("/api/v1/metrics/definitions", json=payload)
    assert first_response.status_code == 201, first_response.text

    same_tenant_duplicate = client.post("/api/v1/metrics/definitions", json=payload)
    assert same_tenant_duplicate.status_code == 400, same_tenant_duplicate.text

    authenticate_client(client, second_admin)
    second_response = client.post("/api/v1/metrics/definitions", json=payload)
    assert second_response.status_code == 201, second_response.text
    assert second_response.json()["data"]["key"] == shared_key
