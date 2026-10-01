import uuid

from app.utils.enums import UserRole
from tests.helpers import authenticate_client


def test_admin_can_create_workflow(
    client,
    create_test_user,
    cleanup_workflows,
):
    admin = create_test_user(
        email=f"workflow-admin-{uuid.uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(
        client,
        admin,
    )

    response = client.post(
        "/api/v1/workflows",
        json={
            "name": "Customer Registration",
            "description": "Customer registration workflow.",
        },
    )

    assert response.status_code == 201

    data = response.json()["data"]

    assert data["name"] == "Customer Registration"
    assert data["status"] == "DRAFT"
    assert data["steps"] == []


def test_workflow_steps_are_ordered(
    client,
    create_test_user,
    cleanup_workflows,
):
    admin = create_test_user(
        email=f"workflow-order-admin-{uuid.uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(
        client,
        admin,
    )

    workflow_response = client.post(
        "/api/v1/workflows",
        json={
            "name": "KYC Review",
        },
    )

    assert workflow_response.status_code == 201

    workflow_id = workflow_response.json()["data"]["id"]

    steps = [
        ("Customer Registration", 1, "Compliance Officer"),
        ("Document Submission", 2, "Reviewer"),
        ("Identity Verification", 3, "Reviewer"),
        ("Compliance Review", 4, "Compliance Officer"),
        ("Approval", 5, "Administrator"),
    ]

    for name, order_number, role in steps:
        response = client.post(
            f"/api/v1/workflows/{workflow_id}/steps",
            json={
                "name": name,
                "order_number": order_number,
                "assigned_role": role,
            },
        )

        assert response.status_code == 201

    response = client.get(
        f"/api/v1/workflows/{workflow_id}",
    )

    assert response.status_code == 200

    result = response.json()["data"]

    assert [step["name"] for step in result["steps"]] == [
        "Customer Registration",
        "Document Submission",
        "Identity Verification",
        "Compliance Review",
        "Approval",
    ]

    assert [step["order_number"] for step in result["steps"]] == [1, 2, 3, 4, 5]


def test_workflow_step_can_be_reordered(
    client,
    create_test_user,
    cleanup_workflows,
):
    admin = create_test_user(
        email=f"workflow-reorder-admin-{uuid.uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(
        client,
        admin,
    )

    workflow_response = client.post(
        "/api/v1/workflows",
        json={
            "name": "Reorder Test Workflow",
        },
    )

    workflow_id = workflow_response.json()["data"]["id"]

    created_steps = []

    for name, order_number in [
        ("Step A", 1),
        ("Step B", 2),
        ("Step C", 3),
    ]:
        response = client.post(
            f"/api/v1/workflows/{workflow_id}/steps",
            json={
                "name": name,
                "order_number": order_number,
                "assigned_role": "Reviewer",
            },
        )

        assert response.status_code == 201
        created_steps.append(response.json()["data"])

    step_c_id = created_steps[2]["id"]

    response = client.put(
        f"/api/v1/workflows/{workflow_id}/steps/{step_c_id}",
        json={
            "order_number": 1,
        },
    )

    assert response.status_code == 200

    response = client.get(
        f"/api/v1/workflows/{workflow_id}",
    )

    assert response.status_code == 200

    names = [step["name"] for step in response.json()["data"]["steps"]]

    assert names == [
        "Step C",
        "Step A",
        "Step B",
    ]


def test_workflow_cannot_be_activated_without_steps(
    client,
    create_test_user,
    cleanup_workflows,
):
    admin = create_test_user(
        email=f"workflow-empty-admin-{uuid.uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(
        client,
        admin,
    )

    workflow_response = client.post(
        "/api/v1/workflows",
        json={
            "name": "Empty Workflow",
        },
    )

    workflow_id = workflow_response.json()["data"]["id"]

    response = client.patch(
        f"/api/v1/workflows/{workflow_id}/status",
        json={
            "status": "ACTIVE",
        },
    )

    assert response.status_code == 400


def test_workflow_execution_tracks_current_step(
    client,
    create_test_user,
    cleanup_workflows,
):
    admin = create_test_user(
        email=f"workflow-exec-admin-{uuid.uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(
        client,
        admin,
    )

    workflow_response = client.post(
        "/api/v1/workflows",
        json={
            "name": "Execution Workflow",
        },
    )

    assert workflow_response.status_code == 201

    workflow_id = workflow_response.json()["data"]["id"]

    for name, order_number, role in [
        ("Step One", 1, "Administrator"),
        ("Step Two", 2, "Administrator"),
        ("Step Three", 3, "Administrator"),
    ]:
        response = client.post(
            f"/api/v1/workflows/{workflow_id}/steps",
            json={
                "name": name,
                "order_number": order_number,
                "assigned_role": role,
            },
        )

        assert response.status_code == 201

    response = client.patch(
        f"/api/v1/workflows/{workflow_id}/status",
        json={
            "status": "ACTIVE",
        },
    )

    assert response.status_code == 200

    entity_id = uuid.uuid4()

    response = client.post(
        f"/api/v1/workflows/{workflow_id}/executions",
        json={
            "entity_type": "CUSTOMER",
            "entity_id": str(entity_id),
            "context": {
                "source": "integration-test",
            },
        },
    )

    assert response.status_code == 201

    execution = response.json()["data"]

    assert execution["status"] == "IN_PROGRESS"
    assert len(execution["step_executions"]) == 3

    assert execution["step_executions"][0]["status"] == "IN_PROGRESS"
    assert execution["step_executions"][1]["status"] == "PENDING"
    assert execution["step_executions"][2]["status"] == "PENDING"

    execution_id = execution["id"]

    response = client.post(
        f"/api/v1/workflows/executions/{execution_id}/advance",
        json={
            "notes": "Completed step one.",
        },
    )

    assert response.status_code == 200

    execution = response.json()["data"]

    assert execution["status"] == "IN_PROGRESS"
    assert execution["step_executions"][0]["status"] == "COMPLETED"
    assert execution["step_executions"][1]["status"] == "IN_PROGRESS"

    response = client.post(
        f"/api/v1/workflows/executions/{execution_id}/advance",
        json={
            "notes": "Completed step two.",
        },
    )

    assert response.status_code == 200

    response = client.post(
        f"/api/v1/workflows/executions/{execution_id}/advance",
        json={
            "notes": "Completed step three.",
        },
    )

    assert response.status_code == 200

    execution = response.json()["data"]

    assert execution["status"] == "COMPLETED"
    assert execution["current_step_id"] is None

    assert [step["status"] for step in execution["step_executions"]] == [
        "COMPLETED",
        "COMPLETED",
        "COMPLETED",
    ]


def test_reviewer_cannot_complete_compliance_officer_step(
    client,
    create_test_user,
    cleanup_workflows,
):
    admin = create_test_user(
        email=f"workflow-rbac-admin-{uuid.uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    reviewer = create_test_user(
        email=f"workflow-rbac-reviewer-{uuid.uuid4()}@example.com",
        role=UserRole.REVIEWER,
    )

    authenticate_client(
        client,
        admin,
    )

    workflow_response = client.post(
        "/api/v1/workflows",
        json={
            "name": "Role Restricted Workflow",
        },
    )

    workflow_id = workflow_response.json()["data"]["id"]

    response = client.post(
        f"/api/v1/workflows/{workflow_id}/steps",
        json={
            "name": "Compliance Review",
            "order_number": 1,
            "assigned_role": "Compliance Officer",
        },
    )

    assert response.status_code == 201

    response = client.patch(
        f"/api/v1/workflows/{workflow_id}/status",
        json={
            "status": "ACTIVE",
        },
    )

    assert response.status_code == 200

    response = client.post(
        f"/api/v1/workflows/{workflow_id}/executions",
        json={
            "entity_type": "COMPLIANCE_CASE",
            "entity_id": str(uuid.uuid4()),
        },
    )

    assert response.status_code == 201

    execution_id = response.json()["data"]["id"]

    authenticate_client(
        client,
        reviewer,
    )

    response = client.post(
        f"/api/v1/workflows/executions/{execution_id}/advance",
        json={},
    )

    assert response.status_code == 403


def test_non_admin_cannot_create_workflow(
    client,
    create_test_user,
):
    reviewer = create_test_user(
        email=f"workflow-non-admin-{uuid.uuid4()}@example.com",
        role=UserRole.REVIEWER,
    )

    authenticate_client(
        client,
        reviewer,
    )

    response = client.post(
        "/api/v1/workflows",
        json={
            "name": "Unauthorized Workflow",
        },
    )

    assert response.status_code == 403
