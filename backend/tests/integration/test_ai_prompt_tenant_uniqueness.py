"""Regression coverage for tenant-local AI prompt uniqueness."""

from uuid import uuid4

from app.models.ai_prompt import AIPrompt
from app.models.ai_prompt_assignment import AIPromptAssignment
from app.utils.enums import AIFunction, UserRole
from tests.helpers import authenticate_client


def _create_activate_and_assign_prompt(client, name: str) -> str:
    create_response = client.post(
        "/api/v1/ai-prompts",
        json={
            "name": name,
            "purpose": "Tenant-local prompt uniqueness regression test.",
            "prompt_text": "Use the tenant's configured prompt instructions.",
        },
    )
    assert create_response.status_code == 201, create_response.text

    payload: object = create_response.json()
    assert isinstance(payload, dict), "Expected a JSON object response."

    data = payload.get("data")
    assert isinstance(data, dict), "Expected a data object in the response."

    prompt_id = data.get("id")
    assert isinstance(prompt_id, str), "Expected prompt ID to be a string."

    activate_response = client.patch(
        f"/api/v1/ai-prompts/{prompt_id}/status",
        json={"status": "ACTIVE"},
    )
    assert activate_response.status_code == 200, activate_response.text

    assignment_response = client.post(
        "/api/v1/ai-prompts/assignments",
        json={
            "ai_function": AIFunction.DOCUMENT_EXTRACTION.value,
            "prompt_id": prompt_id,
        },
    )
    assert assignment_response.status_code == 200, assignment_response.text

    return prompt_id


def test_prompt_name_and_ai_function_can_be_reused_by_another_tenant(
    client,
    db_session,
    create_test_user,
    create_test_tenant,
    cleanup_ai_prompts,
):
    """Both tenants can activate the same prompt name and assign one function."""
    first_admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email=f"ai-prompt-tenant-first-{uuid4()}@example.com",
    )
    second_tenant = create_test_tenant()
    second_admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email=f"ai-prompt-tenant-second-{uuid4()}@example.com",
        tenant_id=second_tenant.id,
    )
    shared_name = f"tenant-local-prompt-{uuid4().hex}"

    try:
        authenticate_client(client, first_admin)
        first_prompt_id = _create_activate_and_assign_prompt(client, shared_name)

        authenticate_client(client, second_admin)
        second_prompt_id = _create_activate_and_assign_prompt(client, shared_name)

        assert first_prompt_id != second_prompt_id

        second_assignment = client.get(
            f"/api/v1/ai-prompts/assignments/{AIFunction.DOCUMENT_EXTRACTION.value}"
        )
        assert second_assignment.status_code == 200, second_assignment.text
        assert second_assignment.json()["data"]["prompt_id"] == second_prompt_id

        authenticate_client(client, first_admin)
        first_assignment = client.get(
            f"/api/v1/ai-prompts/assignments/{AIFunction.DOCUMENT_EXTRACTION.value}"
        )
        assert first_assignment.status_code == 200, first_assignment.text
        assert first_assignment.json()["data"]["prompt_id"] == first_prompt_id
    finally:
        # The shared cleanup_ai_prompts fixture intentionally covers only the
        # default tenant. Remove this test's second-tenant records before that
        # tenant's fixture attempts to delete its creator user.
        db_session.info["tenant_id"] = second_tenant.id
        db_session.query(AIPromptAssignment).filter(
            AIPromptAssignment.tenant_id == second_tenant.id
        ).delete(synchronize_session=False)
        db_session.query(AIPrompt).filter(
            AIPrompt.tenant_id == second_tenant.id
        ).delete(synchronize_session=False)
        db_session.commit()
