import pytest

from app.models.ai_interaction import AIInteraction
from app.models.ai_prompt import AIPrompt
from app.models.ai_prompt_assignment import AIPromptAssignment
from app.utils.enums import (
    AIFunction,
    AIPromptStatus,
    UserRole,
)
from tests.conftest import TestSessionLocal
from tests.helpers import (
    authenticate_client,
    create_customer_with_data,
    create_verification_case,
)
from tests.seed import seed_ai_prompts


@pytest.fixture(autouse=True)
def seed_ai_assistant_data():
    db = TestSessionLocal()

    try:
        seed_ai_prompts(db)
    finally:
        db.close()


def create_active_prompt(
    db_session,
    *,
    name: str,
    purpose: str,
    prompt_text: str,
    created_by,
):
    prompt = AIPrompt(
        name=name,
        purpose=purpose,
        prompt_text=prompt_text,
        version=1,
        status=AIPromptStatus.ACTIVE,
        created_by=created_by,
    )

    db_session.add(prompt)
    db_session.commit()
    db_session.refresh(prompt)

    return prompt


def create_prompt_assignment(
    db_session,
    *,
    ai_function: AIFunction,
    prompt_id,
):
    assignment = AIPromptAssignment(
        ai_function=ai_function,
        prompt_id=prompt_id,
    )

    db_session.add(assignment)
    db_session.commit()
    db_session.refresh(assignment)

    return assignment


def test_compliance_officer_can_send_ai_request(
    client,
    create_test_user,
    cleanup_test_customers,
    cleanup_ai_prompts,
    cleanup_ai_interactions,
):
    admin = create_test_user(
        email="officer-send@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    response = create_customer_with_data(
        client,
        name="officer",
    )

    customer_id = response.json()["data"]["id"]

    case = create_verification_case(client, customer_id)
    case_id = case["id"]

    compliance_officer = create_test_user(
        email="ai-compliance@example.com",
        role=UserRole.COMPLIANCE_OFFICER,
    )

    authenticate_client(client, compliance_officer)

    response = client.post(
        "/api/v1/ai-assistant/ask",
        json={
            "ai_function": "CASE_SUMMARY",
            "question": "Summarize this compliance case.",
            "customer_id": customer_id,
            "verification_case_id": case_id,
        },
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["interaction_id"] is not None
    assert data["ai_function"] == "CASE_SUMMARY"
    assert data["prompt_id"] is not None
    assert data["status"] == "COMPLETED"
    assert data["provider_name"] == "mock"
    assert data["content"] is not None
    assert data["result"] is not None


def test_ai_request_returns_structured_response(
    client,
    create_test_user,
    cleanup_test_customers,
    cleanup_ai_prompts,
    cleanup_ai_interactions,
):
    admin = create_test_user(
        email="officer-send@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    response = create_customer_with_data(
        client,
        name="officer",
    )

    customer_id = response.json()["data"]["id"]

    case = create_verification_case(client, customer_id)
    case_id = case["id"]

    compliance_officer = create_test_user(
        email="ai-structured@example.com",
        role=UserRole.COMPLIANCE_OFFICER,
    )

    authenticate_client(client, compliance_officer)

    response = client.post(
        "/api/v1/ai-assistant/ask",
        json={
            "ai_function": "CASE_SUMMARY",
            "question": "Summarize this customer's verification status.",
            "verification_case_id": case_id,
            "document_id": customer_id,
        },
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["result"] is not None

    result = data["result"]

    assert "summary" in result
    assert "customer_status" in result
    assert "missing_documents" in result
    assert "findings" in result
    assert "recommendation" in result
    assert "confidence" in result

    assert isinstance(result["summary"], str)
    assert isinstance(result["customer_status"], str)
    assert isinstance(result["missing_documents"], list)
    assert isinstance(result["findings"], list)
    assert isinstance(result["recommendation"], str)
    assert isinstance(result["confidence"], (int, float))


def test_ai_request_is_logged(
    client,
    create_test_user,
    cleanup_test_customers,
    cleanup_ai_prompts,
    cleanup_ai_interactions,
    db_session,
):
    admin = create_test_user(
        email="officer-send@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    response = create_customer_with_data(
        client,
        name="officer",
    )

    customer_id = response.json()["data"]["id"]

    case = create_verification_case(client, customer_id)
    case_id = case["id"]

    compliance_officer = create_test_user(
        email="ai-logged@example.com",
        role=UserRole.COMPLIANCE_OFFICER,
    )

    authenticate_client(client, compliance_officer)

    response = client.post(
        "/api/v1/ai-assistant/ask",
        json={
            "ai_function": "CASE_SUMMARY",
            "question": "Summarize this compliance case.",
            "verification_case_id": case_id,
            "document_id": customer_id,
        },
    )

    assert response.status_code == 200

    interaction_id = response.json()["data"]["interaction_id"]

    interaction = db_session.get(
        AIInteraction,
        interaction_id,
    )

    assert interaction is not None
    assert interaction.user_id == compliance_officer.id
    assert interaction.ai_function == AIFunction.CASE_SUMMARY
    assert interaction.question == ("Summarize this compliance case.")
    assert interaction.status.value == "COMPLETED"
    assert interaction.response_text is not None
    assert interaction.response_data is not None
    assert interaction.provider_name == "mock"
    assert interaction.completed_at is not None


def test_ai_request_uses_assigned_prompt(
    client,
    create_test_user,
    cleanup_test_customers,
    cleanup_ai_prompts,
    cleanup_ai_interactions,
    db_session,
):
    admin = create_test_user(
        email="officer-send@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    response = create_customer_with_data(
        client,
        name="officer",
    )

    customer_id = response.json()["data"]["id"]

    case = create_verification_case(client, customer_id)
    case_id = case["id"]

    compliance_officer = create_test_user(
        email="ai-prompt-user@example.com",
        role=UserRole.COMPLIANCE_OFFICER,
    )

    authenticate_client(client, compliance_officer)

    response = client.post(
        "/api/v1/ai-assistant/ask",
        json={
            "ai_function": "CASE_SUMMARY",
            "question": "Summarize this case.",
            "verification_case_id": case_id,
            "customer_id": customer_id,
        },
    )

    assert response.status_code == 200

    data = response.json()["data"]

    interaction_id = data["interaction_id"]

    interaction = db_session.get(
        AIInteraction,
        interaction_id,
    )

    assert interaction is not None


def test_ai_request_requires_authentication(
    client,
    cleanup_ai_prompts,
):
    response = client.post(
        "/api/v1/ai-assistant/ask",
        json={
            "ai_function": "CASE_SUMMARY",
            "question": "Summarize this compliance case.",
        },
    )

    assert response.status_code == 401


@pytest.mark.parametrize(
    "role",
    [
        UserRole.ADMINISTRATOR,
        UserRole.COMPLIANCE_OFFICER,
        UserRole.REVIEWER,
    ],
)
def test_ai_request_allowed_roles(
    client,
    create_test_user,
    cleanup_test_customers,
    cleanup_ai_prompts,
    cleanup_ai_interactions,
    role,
):
    admin = create_test_user(
        email="officer-send@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    response = create_customer_with_data(
        client,
        name="officer",
    )

    customer_id = response.json()["data"]["id"]

    case = create_verification_case(client, customer_id)
    case_id = case["id"]

    user = create_test_user(
        email=(f"ai-role-{role.value.lower().replace(' ', '-')}@example.com"),
        role=role,
    )

    authenticate_client(client, user)

    response = client.post(
        "/api/v1/ai-assistant/ask",
        json={
            "ai_function": "CASE_SUMMARY",
            "question": "Summarize this compliance case.",
            "verification_case_id": case_id,
            "customer_id": customer_id,
        },
    )

    assert response.status_code == 200


def test_auditor_cannot_send_ai_request(
    client,
    create_test_user,
    cleanup_test_customers,
    cleanup_ai_prompts,
):
    admin = create_test_user(
        email="officer-send@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    response = create_customer_with_data(
        client,
        name="officer",
    )

    customer_id = response.json()["data"]["id"]

    case = create_verification_case(client, customer_id)
    case_id = case["id"]

    auditor = create_test_user(
        email="ai-auditor@example.com",
        role=UserRole.AUDITOR,
    )

    authenticate_client(client, auditor)

    response = client.post(
        "/api/v1/ai-assistant/ask",
        json={
            "ai_function": "CASE_SUMMARY",
            "question": "Summarize this compliance case.",
            "verification_case_id": case_id,
            "customer_id": customer_id,
        },
    )

    assert response.status_code == 403


def test_ai_interaction_can_be_retrieved(
    client,
    create_test_user,
    cleanup_test_customers,
    cleanup_ai_prompts,
    cleanup_ai_interactions,
):
    admin = create_test_user(
        email="officer-send@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    response = create_customer_with_data(
        client,
        name="officer",
    )

    customer_id = response.json()["data"]["id"]

    case = create_verification_case(client, customer_id)
    case_id = case["id"]

    compliance_officer = create_test_user(
        email="ai-retrieve@example.com",
        role=UserRole.COMPLIANCE_OFFICER,
    )

    authenticate_client(client, compliance_officer)

    create_response = client.post(
        "/api/v1/ai-assistant/ask",
        json={
            "ai_function": "CASE_SUMMARY",
            "question": "Summarize this compliance case.",
            "verification_case_id": case_id,
            "customer_id": customer_id,
        },
    )

    assert create_response.status_code == 200

    interaction_id = create_response.json()["data"]["interaction_id"]

    response = client.get(
        f"/api/v1/ai-assistant/interactions/{interaction_id}",
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["id"] == interaction_id
    assert data["user_id"] == str(compliance_officer.id)
    assert data["ai_function"] == "CASE_SUMMARY"
    assert data["question"] == ("Summarize this compliance case.")
    assert data["status"] == "COMPLETED"


def test_ai_interaction_belongs_to_requesting_user(
    client,
    create_test_user,
    cleanup_test_customers,
    cleanup_ai_prompts,
    cleanup_ai_interactions,
):
    admin = create_test_user(
        email="officer-send@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    response = create_customer_with_data(
        client,
        name="officer",
    )

    customer_id = response.json()["data"]["id"]

    case = create_verification_case(client, customer_id)
    case_id = case["id"]

    first_user = create_test_user(
        email="ai-owner-one@example.com",
        role=UserRole.COMPLIANCE_OFFICER,
    )

    second_user = create_test_user(
        email="ai-owner-two@example.com",
        role=UserRole.COMPLIANCE_OFFICER,
    )

    authenticate_client(client, first_user)

    create_response = client.post(
        "/api/v1/ai-assistant/ask",
        json={
            "ai_function": "CASE_SUMMARY",
            "question": "Summarize this compliance case.",
            "verification_case_id": case_id,
            "customer_id": customer_id,
        },
    )

    assert create_response.status_code == 200

    interaction_id = create_response.json()["data"]["interaction_id"]

    client.headers.pop("Authorization")

    authenticate_client(client, second_user)

    response = client.get(
        f"/api/v1/ai-assistant/interactions/{interaction_id}",
    )

    assert response.status_code == 400


def test_ai_request_with_customer_context(
    client,
    create_test_user,
    cleanup_test_customers,
    cleanup_ai_prompts,
    cleanup_ai_interactions,
):
    compliance_officer = create_test_user(
        email="ai-customer-context@example.com",
        role=UserRole.COMPLIANCE_OFFICER,
    )

    admin = create_test_user(
        email="ai-customer-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    customer_response = create_customer_with_data(
        client,
        email="ai-context-customer@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    client.headers.pop("Authorization")

    authenticate_client(client, compliance_officer)

    response = client.post(
        "/api/v1/ai-assistant/ask",
        json={
            "ai_function": "CUSTOMER_SUMMARY",
            "question": "Summarize this customer.",
            "customer_id": customer_id,
        },
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["ai_function"] == "CUSTOMER_SUMMARY"
    assert data["interaction_id"] is not None
    assert data["result"] is not None


def test_ai_request_with_case_context(
    client,
    create_test_user,
    cleanup_test_customers,
    cleanup_ai_prompts,
    cleanup_ai_interactions,
):
    compliance_officer = create_test_user(
        email="ai-case-context@example.com",
        role=UserRole.COMPLIANCE_OFFICER,
    )

    admin = create_test_user(
        email="ai-case-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    customer_response = create_customer_with_data(
        client,
        email="ai-case-customer@example.com",
    )

    assert customer_response.status_code == 201

    customer_id = customer_response.json()["data"]["id"]

    case = create_verification_case(
        client,
        customer_id,
    )

    client.headers.pop("Authorization")

    authenticate_client(client, compliance_officer)

    response = client.post(
        "/api/v1/ai-assistant/ask",
        json={
            "ai_function": "CASE_SUMMARY",
            "question": "Summarize this verification case.",
            "customer_id": customer_id,
            "verification_case_id": case["id"],
        },
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["ai_function"] == "CASE_SUMMARY"
    assert data["interaction_id"] is not None
    assert data["result"] is not None
