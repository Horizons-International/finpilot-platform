"""Regression tests for tenant-local AI prompt names and assignments."""

from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.models.ai_prompt import AIPrompt
from app.models.ai_prompt_assignment import AIPromptAssignment
from app.models.audit_log import AuditLog
from app.utils.enums import AIFunction, AIPromptStatus, UserRole
from tests.helpers import authenticate_client


def _create_prompt(client: TestClient, name: str) -> dict[str, object]:
    response = client.post(
        "/api/v1/ai-prompts",
        json={
            "name": name,
            "purpose": "Tenant-isolation regression test.",
            "prompt_text": "Apply the tenant-specific test prompt.",
        },
    )
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert isinstance(data, dict)
    return data


def _activate_prompt(client: TestClient, prompt_id: str) -> None:
    response = client.patch(
        f"/api/v1/ai-prompts/{prompt_id}/status",
        json={"status": AIPromptStatus.ACTIVE.value},
    )
    assert response.status_code == 200, response.text


def _assign_prompt(
    client: TestClient,
    prompt_id: str,
    ai_function: AIFunction,
) -> dict[str, object]:
    response = client.post(
        "/api/v1/ai-prompts/assignments",
        json={"ai_function": ai_function.value, "prompt_id": prompt_id},
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert isinstance(data, dict)
    return data


@pytest.fixture
def cleanup_ai_prompt_tenant_isolation(
    db_session,
    create_test_tenant,
    create_test_user,
):
    """Remove prompts and assignments created by this test across all tenants."""
    existing_prompt_ids = {
        prompt_id for (prompt_id,) in db_session.query(AIPrompt.id).all()
    }
    del create_test_tenant, create_test_user
    yield

    db_session.expire_all()
    created_prompt_ids = {
        prompt_id
        for (prompt_id,) in db_session.query(AIPrompt.id).all()
        if prompt_id not in existing_prompt_ids
    }
    if created_prompt_ids:
        db_session.query(AIPromptAssignment).filter(
            AIPromptAssignment.prompt_id.in_(created_prompt_ids)
        ).delete(synchronize_session=False)
        db_session.query(AuditLog).filter(
            AuditLog.resource_type == "ai_prompt",
            AuditLog.resource_id.in_(created_prompt_ids),
        ).delete(synchronize_session=False)
        db_session.query(AIPrompt).filter(AIPrompt.id.in_(created_prompt_ids)).delete(
            synchronize_session=False
        )
        db_session.commit()


def test_ai_prompt_names_and_function_assignments_are_tenant_local(
    client: TestClient,
    db_session,
    create_test_user,
    create_test_tenant,
    default_tenant_id,
    cleanup_ai_prompt_tenant_isolation,
):
    """Different tenants can reuse prompt names and AI functions safely."""
    tenant_b = create_test_tenant(code=f"AI-ISOLATION-{uuid4().hex[:8].upper()}")
    admin_a = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email=f"ai-tenant-a-{uuid4()}@example.com",
        tenant_id=default_tenant_id,
    )
    admin_b = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email=f"ai-tenant-b-{uuid4()}@example.com",
        tenant_id=tenant_b.id,
    )
    shared_name = f"shared-tenant-prompt-{uuid4().hex}"
    shared_function = AIFunction.RISK_ANALYSIS

    authenticate_client(client, admin_a)
    prompt_a = _create_prompt(client, shared_name)
    prompt_a_id = UUID(str(prompt_a["id"]))
    version_a_response = client.post(
        f"/api/v1/ai-prompts/{prompt_a_id}/versions",
        json={"prompt_text": "Tenant A's second prompt version."},
    )
    assert version_a_response.status_code == 201, version_a_response.text
    _activate_prompt(client, str(prompt_a_id))
    versions_a_response = client.get(f"/api/v1/ai-prompts/{prompt_a_id}/versions")
    assert versions_a_response.status_code == 200, versions_a_response.text
    versions_a = versions_a_response.json()["data"]
    assert len(versions_a) == 2
    assert {item["prompt_text"] for item in versions_a} == {
        "Apply the tenant-specific test prompt.",
        "Tenant A's second prompt version.",
    }
    assignment_a = _assign_prompt(client, str(prompt_a_id), shared_function)
    assert assignment_a["prompt_id"] == str(prompt_a_id)

    # A duplicate name within one tenant must remain invalid.
    duplicate_response = client.post(
        "/api/v1/ai-prompts",
        json={
            "name": shared_name,
            "purpose": "Duplicate in the same tenant.",
            "prompt_text": "This must be rejected.",
        },
    )
    assert duplicate_response.status_code == 400, duplicate_response.text

    authenticate_client(client, admin_b)
    prompt_b = _create_prompt(client, shared_name)
    prompt_b_id = UUID(str(prompt_b["id"]))
    version_b_response = client.post(
        f"/api/v1/ai-prompts/{prompt_b_id}/versions",
        json={"prompt_text": "Tenant B's second prompt version."},
    )
    assert version_b_response.status_code == 201, version_b_response.text
    _activate_prompt(client, str(prompt_b_id))
    versions_b_response = client.get(f"/api/v1/ai-prompts/{prompt_b_id}/versions")
    assert versions_b_response.status_code == 200, versions_b_response.text
    versions_b = versions_b_response.json()["data"]
    assert len(versions_b) == 2
    assert {item["prompt_text"] for item in versions_b} == {
        "Apply the tenant-specific test prompt.",
        "Tenant B's second prompt version.",
    }
    assignment_b = _assign_prompt(client, str(prompt_b_id), shared_function)
    assert assignment_b["prompt_id"] == str(prompt_b_id)

    # The same function resolves to the current tenant's own assignment.
    assignment_response_b = client.get(
        f"/api/v1/ai-prompts/assignments/{shared_function.value}"
    )
    assert assignment_response_b.status_code == 200, assignment_response_b.text
    assert assignment_response_b.json()["data"]["prompt_id"] == str(prompt_b_id)

    # Cross-tenant IDs are not visible, even when the prompt name is identical.
    assert client.get(f"/api/v1/ai-prompts/{prompt_a_id}").status_code == 404

    authenticate_client(client, admin_a)
    assignment_response_a = client.get(
        f"/api/v1/ai-prompts/assignments/{shared_function.value}"
    )
    assert assignment_response_a.status_code == 200, assignment_response_a.text
    assert assignment_response_a.json()["data"]["prompt_id"] == str(prompt_a_id)
    assert client.get(f"/api/v1/ai-prompts/{prompt_b_id}").status_code == 404

    list_response = client.get("/api/v1/ai-prompts")
    assert list_response.status_code == 200, list_response.text
    listed_ids = {item["id"] for item in list_response.json()["data"]}
    assert str(prompt_a_id) in listed_ids
    assert str(prompt_b_id) not in listed_ids

    # Confirm the persisted rows retain their distinct tenant ownership.
    stored = (
        db_session.query(AIPrompt)
        .filter(AIPrompt.id.in_([prompt_a_id, prompt_b_id]))
        .all()
    )
    assert {row.tenant_id for row in stored} == {default_tenant_id, tenant_b.id}
    assignments = (
        db_session.query(AIPromptAssignment)
        .filter(AIPromptAssignment.ai_function == shared_function)
        .all()
    )
    matching = [
        row for row in assignments if row.prompt_id in {prompt_a_id, prompt_b_id}
    ]
    assert len(matching) == 2
    assert {row.tenant_id for row in matching} == {default_tenant_id, tenant_b.id}
