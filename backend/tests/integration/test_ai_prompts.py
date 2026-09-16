from uuid import UUID, uuid4

from app.ai.prompts.loader import AIPromptLoader
from app.models.ai_prompt import AIPrompt
from app.models.ai_prompt_assignment import AIPromptAssignment
from app.models.audit_log import AuditLog
from app.utils.enums import (
    AIFunction,
    AIPromptStatus,
    AuditEventType,
    UserRole,
)
from tests.helpers import authenticate_client


def create_prompt(
    client,
    name: str = "document-extraction",
    purpose: str = "Extract structured information from documents.",
    prompt_text: str = "Extract the required fields from this document.",
):
    return client.post(
        "/api/v1/ai-prompts",
        json={
            "name": name,
            "purpose": purpose,
            "prompt_text": prompt_text,
        },
    )


def create_prompt_version(
    client,
    prompt_id,
    prompt_text: str = "Updated document extraction instructions.",
):
    return client.post(
        f"/api/v1/ai-prompts/{prompt_id}/versions",
        json={
            "prompt_text": prompt_text,
        },
    )


def update_prompt_status(
    client,
    prompt_id,
    status: str,
):
    return client.patch(
        f"/api/v1/ai-prompts/{prompt_id}/status",
        json={
            "status": status,
        },
    )


def test_administrator_can_create_ai_prompt(
    client,
    create_test_user,
    cleanup_ai_prompts,
):
    admin_user = create_test_user(
        email="ai-prompt-create-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin_user)

    response = create_prompt(client)

    assert response.status_code == 201

    data = response.json()["data"]

    assert data["name"] == "document-extraction"
    assert data["purpose"] == ("Extract structured information from documents.")
    assert data["prompt_text"] == ("Extract the required fields from this document.")
    assert data["version"] == 1
    assert data["status"] == "INACTIVE"
    assert data["created_by"] == str(admin_user.id)


def test_ai_prompt_creation_is_audited(
    client,
    db_session,
    create_test_user,
    cleanup_ai_prompts,
):
    admin_user = create_test_user(
        email="ai-prompt-audit-create@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin_user)

    response = create_prompt(
        client,
        name="audit-document-extraction",
    )

    assert response.status_code == 201

    prompt_id = response.json()["data"]["id"]

    audit_log = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.event_type == AuditEventType.AI_PROMPT_CREATED,
            AuditLog.resource_type == "ai_prompt",
            AuditLog.resource_id == prompt_id,
        )
        .order_by(AuditLog.timestamp.desc())
        .first()
    )

    assert audit_log is not None
    assert audit_log.user_id == admin_user.id
    assert audit_log.email == admin_user.email


def test_compliance_officer_cannot_create_ai_prompt(
    client,
    create_test_user,
    cleanup_ai_prompts,
):
    compliance_officer = create_test_user(
        email="ai-prompt-create-compliance@example.com",
        role=UserRole.COMPLIANCE_OFFICER,
    )

    authenticate_client(client, compliance_officer)

    response = create_prompt(client)

    assert response.status_code == 403


def test_reviewer_cannot_create_ai_prompt(
    client,
    create_test_user,
    cleanup_ai_prompts,
):
    reviewer = create_test_user(
        email="ai-prompt-create-reviewer@example.com",
        role=UserRole.REVIEWER,
    )

    authenticate_client(client, reviewer)

    response = create_prompt(client)

    assert response.status_code == 403


def test_auditor_cannot_create_ai_prompt(
    client,
    create_test_user,
    cleanup_ai_prompts,
):
    auditor = create_test_user(
        email="ai-prompt-create-auditor@example.com",
        role=UserRole.AUDITOR,
    )

    authenticate_client(client, auditor)

    response = create_prompt(client)

    assert response.status_code == 403


def test_duplicate_ai_prompt_name_is_rejected(
    client,
    create_test_user,
    cleanup_ai_prompts,
):
    admin_user = create_test_user(
        email="ai-prompt-duplicate@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin_user)

    first_response = create_prompt(
        client,
        name="duplicate-prompt",
    )

    assert first_response.status_code == 201

    second_response = create_prompt(
        client,
        name="duplicate-prompt",
        prompt_text="A different prompt.",
    )

    assert second_response.status_code == 400


def test_get_ai_prompts(
    client,
    create_test_user,
    cleanup_ai_prompts,
):
    admin_user = create_test_user(
        email="ai-prompt-list@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin_user)

    create_response = create_prompt(
        client,
        name="list-prompt",
    )

    assert create_response.status_code == 201

    response = client.get("/api/v1/ai-prompts")

    assert response.status_code == 200
    assert isinstance(response.json()["data"], list)


def test_get_active_ai_prompts_returns_only_active_prompts(
    client,
    create_test_user,
    cleanup_ai_prompts,
):
    admin_user = create_test_user(
        email="ai-prompt-active-list@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin_user)

    create_response = create_prompt(
        client,
        name="active-list-prompt",
    )

    assert create_response.status_code == 201

    prompt_id = create_response.json()["data"]["id"]

    activate_response = update_prompt_status(
        client,
        prompt_id,
        "ACTIVE",
    )

    assert activate_response.status_code == 200

    response = client.get("/api/v1/ai-prompts/active")

    assert response.status_code == 200

    prompts = response.json()["data"]

    assert all(prompt["status"] == "ACTIVE" for prompt in prompts)

    ids = {prompt["id"] for prompt in prompts}

    assert prompt_id in ids


def test_get_ai_prompt_by_id(
    client,
    create_test_user,
    cleanup_ai_prompts,
):
    admin_user = create_test_user(
        email="ai-prompt-get@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin_user)

    create_response = create_prompt(
        client,
        name="get-by-id-prompt",
    )

    assert create_response.status_code == 201

    prompt_id = create_response.json()["data"]["id"]

    response = client.get(
        f"/api/v1/ai-prompts/{prompt_id}",
    )

    assert response.status_code == 200
    assert response.json()["data"]["id"] == prompt_id


def test_get_nonexistent_ai_prompt(
    client,
    create_test_user,
    cleanup_ai_prompts,
):
    admin_user = create_test_user(
        email="ai-prompt-not-found@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin_user)

    response = client.get(
        f"/api/v1/ai-prompts/{uuid4()}",
    )

    assert response.status_code == 404


def test_create_ai_prompt_version(
    client,
    create_test_user,
    cleanup_ai_prompts,
):
    admin_user = create_test_user(
        email="ai-prompt-version@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin_user)

    create_response = create_prompt(
        client,
        name="versioned-prompt",
        prompt_text="Version one.",
    )

    assert create_response.status_code == 201

    prompt_id = create_response.json()["data"]["id"]

    version_response = create_prompt_version(
        client,
        prompt_id,
        prompt_text="Version two.",
    )

    assert version_response.status_code == 201

    data = version_response.json()["data"]

    assert data["name"] == "versioned-prompt"
    assert data["prompt_text"] == "Version two."
    assert data["version"] == 2
    assert data["status"] == "INACTIVE"


def test_create_ai_prompt_version_does_not_modify_previous_version(
    client,
    create_test_user,
    cleanup_ai_prompts,
):
    admin_user = create_test_user(
        email="ai-prompt-version-immutable@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin_user)

    create_response = create_prompt(
        client,
        name="immutable-prompt",
        prompt_text="Original prompt.",
    )

    assert create_response.status_code == 201

    prompt_id = create_response.json()["data"]["id"]

    version_response = create_prompt_version(
        client,
        prompt_id,
        prompt_text="New version.",
    )

    assert version_response.status_code == 201

    response = client.get(
        f"/api/v1/ai-prompts/{prompt_id}/versions",
    )

    assert response.status_code == 200

    versions = response.json()["data"]

    assert len(versions) == 2

    versions_by_number = {version["version"]: version for version in versions}

    assert versions_by_number[1]["prompt_text"] == "Original prompt."
    assert versions_by_number[1]["status"] == "INACTIVE"

    assert versions_by_number[2]["prompt_text"] == "New version."
    assert versions_by_number[2]["status"] == "INACTIVE"


def test_get_ai_prompt_versions(
    client,
    create_test_user,
    cleanup_ai_prompts,
):
    admin_user = create_test_user(
        email="ai-prompt-version-list@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin_user)

    create_response = create_prompt(
        client,
        name="version-list-prompt",
    )

    assert create_response.status_code == 201

    prompt_id = create_response.json()["data"]["id"]

    version_response = create_prompt_version(
        client,
        prompt_id,
    )

    assert version_response.status_code == 201

    response = client.get(
        f"/api/v1/ai-prompts/{prompt_id}/versions",
    )

    assert response.status_code == 200

    versions = response.json()["data"]

    assert len(versions) == 2
    assert {version["version"] for version in versions} == {1, 2}


def test_activate_ai_prompt(
    client,
    create_test_user,
    cleanup_ai_prompts,
):
    admin_user = create_test_user(
        email="ai-prompt-activate@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin_user)

    create_response = create_prompt(
        client,
        name="activate-prompt",
    )

    assert create_response.status_code == 201

    prompt_id = create_response.json()["data"]["id"]

    response = update_prompt_status(
        client,
        prompt_id,
        "ACTIVE",
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["status"] == "ACTIVE"


def test_deactivate_ai_prompt(
    client,
    create_test_user,
    cleanup_ai_prompts,
):
    admin_user = create_test_user(
        email="ai-prompt-deactivate@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin_user)

    create_response = create_prompt(
        client,
        name="deactivate-prompt",
    )

    assert create_response.status_code == 201

    prompt_id = create_response.json()["data"]["id"]

    activate_response = update_prompt_status(
        client,
        prompt_id,
        "ACTIVE",
    )

    assert activate_response.status_code == 200

    deactivate_response = update_prompt_status(
        client,
        prompt_id,
        "INACTIVE",
    )

    assert deactivate_response.status_code == 200

    assert deactivate_response.json()["data"]["status"] == "INACTIVE"


def test_same_prompt_name_cannot_have_two_active_versions(
    client,
    create_test_user,
    cleanup_ai_prompts,
):
    admin_user = create_test_user(
        email="ai-prompt-two-active@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin_user)

    create_response = create_prompt(
        client,
        name="single-active-prompt",
        prompt_text="Version one.",
    )

    assert create_response.status_code == 201

    prompt_id = create_response.json()["data"]["id"]

    version_response = create_prompt_version(
        client,
        prompt_id,
        prompt_text="Version two.",
    )

    assert version_response.status_code == 201

    version_two_id = version_response.json()["data"]["id"]

    activate_response = update_prompt_status(
        client,
        prompt_id,
        "ACTIVE",
    )

    assert activate_response.status_code == 200

    second_activate_response = update_prompt_status(
        client,
        version_two_id,
        "ACTIVE",
    )

    assert second_activate_response.status_code == 400


def test_only_active_prompt_can_be_assigned(
    client,
    create_test_user,
    cleanup_ai_prompts,
):
    admin_user = create_test_user(
        email="ai-prompt-assignment-inactive@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin_user)

    create_response = create_prompt(
        client,
        name="inactive-assignment-prompt",
    )

    assert create_response.status_code == 201

    prompt_id = create_response.json()["data"]["id"]

    response = client.post(
        "/api/v1/ai-prompts/assignments",
        json={
            "ai_function": AIFunction.DOCUMENT_EXTRACTION.value,
            "prompt_id": prompt_id,
        },
    )

    assert response.status_code == 400


def test_active_prompt_can_be_assigned(
    client,
    create_test_user,
    cleanup_ai_prompts,
):
    admin_user = create_test_user(
        email="ai-prompt-assignment-active@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin_user)

    create_response = create_prompt(
        client,
        name="active-assignment-prompt",
    )

    assert create_response.status_code == 201

    prompt_id = create_response.json()["data"]["id"]

    activate_response = update_prompt_status(
        client,
        prompt_id,
        "ACTIVE",
    )

    assert activate_response.status_code == 200

    response = client.post(
        "/api/v1/ai-prompts/assignments",
        json={
            "ai_function": AIFunction.DOCUMENT_EXTRACTION.value,
            "prompt_id": prompt_id,
        },
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["ai_function"] == (AIFunction.DOCUMENT_EXTRACTION.value)
    assert data["prompt_id"] == prompt_id


def test_prompt_assignment_can_be_replaced(
    client,
    create_test_user,
    cleanup_ai_prompts,
):
    admin_user = create_test_user(
        email="ai-prompt-reassignment@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin_user)

    first_response = create_prompt(
        client,
        name="first-assigned-prompt",
    )

    assert first_response.status_code == 201

    first_prompt_id = first_response.json()["data"]["id"]

    activate_response = update_prompt_status(
        client,
        first_prompt_id,
        "ACTIVE",
    )

    assert activate_response.status_code == 200

    first_assignment = client.post(
        "/api/v1/ai-prompts/assignments",
        json={
            "ai_function": AIFunction.DOCUMENT_EXTRACTION.value,
            "prompt_id": first_prompt_id,
        },
    )

    assert first_assignment.status_code == 200

    second_response = create_prompt(
        client,
        name="second-assigned-prompt",
    )

    assert second_response.status_code == 201

    second_prompt_id = second_response.json()["data"]["id"]

    activate_response = update_prompt_status(
        client,
        second_prompt_id,
        "ACTIVE",
    )

    assert activate_response.status_code == 200

    second_assignment = client.post(
        "/api/v1/ai-prompts/assignments",
        json={
            "ai_function": AIFunction.DOCUMENT_EXTRACTION.value,
            "prompt_id": second_prompt_id,
        },
    )

    assert second_assignment.status_code == 200

    data = second_assignment.json()["data"]

    assert data["prompt_id"] == second_prompt_id


def test_get_prompt_assignment(
    client,
    create_test_user,
    cleanup_ai_prompts,
):
    admin_user = create_test_user(
        email="ai-prompt-get-assignment@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin_user)

    create_response = create_prompt(
        client,
        name="get-assignment-prompt",
    )

    assert create_response.status_code == 201

    prompt_id = create_response.json()["data"]["id"]

    activate_response = update_prompt_status(
        client,
        prompt_id,
        "ACTIVE",
    )

    assert activate_response.status_code == 200

    assignment_response = client.post(
        "/api/v1/ai-prompts/assignments",
        json={
            "ai_function": AIFunction.DOCUMENT_EXTRACTION.value,
            "prompt_id": prompt_id,
        },
    )

    assert assignment_response.status_code == 200

    response = client.get(
        f"/api/v1/ai-prompts/assignments/{AIFunction.DOCUMENT_EXTRACTION.value}",
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["ai_function"] == (AIFunction.DOCUMENT_EXTRACTION.value)
    assert data["prompt_id"] == prompt_id


def test_get_missing_prompt_assignment_returns_404(
    client,
    create_test_user,
    cleanup_ai_prompts,
):
    admin_user = create_test_user(
        email="ai-prompt-missing-assignment@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin_user)

    response = client.get(
        f"/api/v1/ai-prompts/assignments/{AIFunction.RISK_ANALYSIS.value}",
    )

    assert response.status_code == 404


def test_ai_prompt_activation_is_audited(
    client,
    db_session,
    create_test_user,
    cleanup_ai_prompts,
):
    admin_user = create_test_user(
        email="ai-prompt-audit-activation@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin_user)

    create_response = create_prompt(
        client,
        name="audit-activation-prompt",
    )

    assert create_response.status_code == 201

    prompt_id = create_response.json()["data"]["id"]

    response = update_prompt_status(
        client,
        prompt_id,
        "ACTIVE",
    )

    assert response.status_code == 200

    audit_log = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.event_type == AuditEventType.AI_PROMPT_ACTIVATED,
            AuditLog.resource_type == "ai_prompt",
            AuditLog.resource_id == prompt_id,
        )
        .order_by(AuditLog.timestamp.desc())
        .first()
    )

    assert audit_log is not None
    assert audit_log.user_id == admin_user.id
    assert audit_log.email == admin_user.email


def test_ai_prompt_deactivation_is_audited(
    client,
    db_session,
    create_test_user,
    cleanup_ai_prompts,
):
    admin_user = create_test_user(
        email="ai-prompt-audit-deactivation@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin_user)

    create_response = create_prompt(
        client,
        name="audit-deactivation-prompt",
    )

    assert create_response.status_code == 201

    prompt_id = create_response.json()["data"]["id"]

    activate_response = update_prompt_status(
        client,
        prompt_id,
        "ACTIVE",
    )

    assert activate_response.status_code == 200

    response = update_prompt_status(
        client,
        prompt_id,
        "INACTIVE",
    )

    assert response.status_code == 200

    audit_log = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.event_type == AuditEventType.AI_PROMPT_DEACTIVATED,
            AuditLog.resource_type == "ai_prompt",
            AuditLog.resource_id == prompt_id,
        )
        .order_by(AuditLog.timestamp.desc())
        .first()
    )

    assert audit_log is not None
    assert audit_log.user_id == admin_user.id
    assert audit_log.email == admin_user.email


def test_ai_prompt_version_creation_is_audited(
    client,
    db_session,
    create_test_user,
    cleanup_ai_prompts,
):
    admin_user = create_test_user(
        email="ai-prompt-audit-version@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin_user)

    create_response = create_prompt(
        client,
        name="audit-version-prompt",
    )

    assert create_response.status_code == 201

    prompt_id = create_response.json()["data"]["id"]

    version_response = create_prompt_version(
        client,
        prompt_id,
    )

    assert version_response.status_code == 201

    version_id = version_response.json()["data"]["id"]

    audit_log = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.event_type == AuditEventType.AI_PROMPT_VERSION_CREATED,
            AuditLog.resource_type == "ai_prompt",
            AuditLog.resource_id == version_id,
        )
        .order_by(AuditLog.timestamp.desc())
        .first()
    )

    assert audit_log is not None
    assert audit_log.user_id == admin_user.id
    assert audit_log.email == admin_user.email


def test_ai_prompt_assignment_is_audited(
    client,
    db_session,
    create_test_user,
    cleanup_ai_prompts,
):
    admin_user = create_test_user(
        email="ai-prompt-audit-assignment@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin_user)

    create_response = create_prompt(
        client,
        name="audit-assignment-prompt",
    )

    assert create_response.status_code == 201

    prompt_id = create_response.json()["data"]["id"]

    activate_response = update_prompt_status(
        client,
        prompt_id,
        "ACTIVE",
    )

    assert activate_response.status_code == 200

    assignment_response = client.post(
        "/api/v1/ai-prompts/assignments",
        json={
            "ai_function": AIFunction.COMPLIANCE_REVIEW.value,
            "prompt_id": prompt_id,
        },
    )

    assert assignment_response.status_code == 200

    audit_log = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.event_type == AuditEventType.AI_PROMPT_ASSIGNED,
            AuditLog.resource_type == "ai_prompt",
            AuditLog.resource_id == prompt_id,
        )
        .order_by(AuditLog.timestamp.desc())
        .first()
    )

    assert audit_log is not None
    assert audit_log.user_id == admin_user.id
    assert audit_log.email == admin_user.email


def test_non_admin_cannot_activate_ai_prompt(
    client,
    create_test_user,
    cleanup_ai_prompts,
):
    compliance_officer = create_test_user(
        email="ai-prompt-activate-compliance@example.com",
        role=UserRole.COMPLIANCE_OFFICER,
    )

    admin_user = create_test_user(
        email="ai-prompt-activate-create-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin_user)

    create_response = create_prompt(
        client,
        name="non-admin-activate-prompt",
    )

    assert create_response.status_code == 201

    prompt_id = create_response.json()["data"]["id"]

    authenticate_client(client, compliance_officer)

    response = update_prompt_status(
        client,
        prompt_id,
        "ACTIVE",
    )

    assert response.status_code == 403


def test_non_admin_cannot_create_prompt_version(
    client,
    create_test_user,
    cleanup_ai_prompts,
):
    admin_user = create_test_user(
        email="ai-prompt-version-create-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    compliance_officer = create_test_user(
        email="ai-prompt-version-create-compliance@example.com",
        role=UserRole.COMPLIANCE_OFFICER,
    )

    authenticate_client(client, admin_user)

    create_response = create_prompt(
        client,
        name="non-admin-version-prompt",
    )

    assert create_response.status_code == 201

    prompt_id = create_response.json()["data"]["id"]

    authenticate_client(client, compliance_officer)

    response = create_prompt_version(
        client,
        prompt_id,
    )

    assert response.status_code == 403


def test_ai_prompt_database_record_matches_created_response(
    client,
    db_session,
    create_test_user,
    cleanup_ai_prompts,
):
    admin_user = create_test_user(
        email="ai-prompt-db-record@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin_user)

    response = create_prompt(
        client,
        name="database-prompt",
    )

    assert response.status_code == 201

    prompt_id = response.json()["data"]["id"]

    prompt = db_session.query(AIPrompt).filter(AIPrompt.id == prompt_id).first()

    assert prompt is not None
    assert prompt.name == "database-prompt"
    assert prompt.version == 1
    assert prompt.status == AIPromptStatus.INACTIVE
    assert prompt.created_by == admin_user.id


def test_ai_prompt_assignment_database_record(
    client,
    db_session,
    create_test_user,
    cleanup_ai_prompts,
):
    admin_user = create_test_user(
        email="ai-prompt-assignment-db@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin_user)

    create_response = create_prompt(
        client,
        name="assignment-db-prompt",
    )

    assert create_response.status_code == 201

    prompt_id = create_response.json()["data"]["id"]

    activate_response = update_prompt_status(
        client,
        prompt_id,
        "ACTIVE",
    )

    assert activate_response.status_code == 200

    response = client.post(
        "/api/v1/ai-prompts/assignments",
        json={
            "ai_function": AIFunction.CUSTOMER_SUPPORT.value,
            "prompt_id": prompt_id,
        },
    )

    assert response.status_code == 200

    assignment = (
        db_session.query(AIPromptAssignment)
        .filter(
            AIPromptAssignment.ai_function == AIFunction.CUSTOMER_SUPPORT,
        )
        .first()
    )

    assert assignment is not None
    assert assignment.prompt_id == UUID(prompt_id)


def test_loader_returns_active_assigned_prompt(
    client,
    db_session,
    create_test_user,
    cleanup_ai_prompts,
):
    admin = create_test_user(
        email="ai-prompt-loader@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    prompt = create_prompt(client)

    prompt_id = prompt.json()["data"]["id"]

    update_prompt_status(
        client,
        prompt_id,
        "ACTIVE",
    )

    response = client.post(
        "/api/v1/ai-prompts/assignments",
        json={
            "ai_function": AIFunction.DOCUMENT_EXTRACTION.value,
            "prompt_id": prompt_id,
        },
    )

    assert response.status_code == 200

    loader = AIPromptLoader(db_session)

    loaded_prompt = loader.get_prompt(
        AIFunction.DOCUMENT_EXTRACTION,
    )

    assert loaded_prompt.id == UUID(prompt_id)
    assert loaded_prompt.status == AIPromptStatus.ACTIVE
    assert (
        loaded_prompt.prompt_text == "Extract the required fields from this document."
    )


def test_loader_returns_prompt_text(
    client,
    db_session,
    create_test_user,
    cleanup_ai_prompts,
):
    admin = create_test_user(
        email="ai-prompt-loader-text@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(client, admin)

    prompt = create_prompt(client)

    prompt_id = prompt.json()["data"]["id"]

    update_prompt_status(
        client,
        prompt_id,
        "ACTIVE",
    )

    response = client.post(
        "/api/v1/ai-prompts/assignments",
        json={
            "ai_function": AIFunction.DOCUMENT_EXTRACTION.value,
            "prompt_id": prompt_id,
        },
    )

    assert response.status_code == 200

    loader = AIPromptLoader(db_session)

    prompt_text = loader.get_prompt_text(
        AIFunction.DOCUMENT_EXTRACTION,
    )

    assert prompt_text == "Extract the required fields from this document."


def test_loader_rejects_missing_assignment(
    db_session,
):
    loader = AIPromptLoader(db_session)

    try:
        loader.get_prompt(AIFunction.RISK_ANALYSIS)
    except Exception as exc:
        assert exc.status_code == 404
    else:
        raise AssertionError(
            "Expected missing prompt assignment to raise an exception."
        )
