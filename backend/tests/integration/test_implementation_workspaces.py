"""Integration tests for enterprise implementation workspaces."""

import pytest
from sqlalchemy import select

from app.models.implementation_workspace import (
    ImplementationWorkspace,
    ImplementationWorkspaceComment,
    ImplementationWorkspaceMember,
    ImplementationWorkspaceMilestone,
    ImplementationWorkspaceTask,
)
from app.utils.enums import UserRole
from tests.helpers import authenticate_client

WORKSPACE_URL = "/api/v1/implementation-workspaces"


@pytest.fixture
def cleanup_implementation_workspaces(db_session):
    existing_ids = set(db_session.scalars(select(ImplementationWorkspace.id)).all())
    yield
    all_ids = set(db_session.scalars(select(ImplementationWorkspace.id)).all())
    new_ids = all_ids - existing_ids
    if not new_ids:
        return

    for model in (
        ImplementationWorkspaceComment,
        ImplementationWorkspaceTask,
        ImplementationWorkspaceMilestone,
        ImplementationWorkspaceMember,
    ):
        db_session.query(model).filter(model.workspace_id.in_(new_ids)).delete(
            synchronize_session=False
        )
    db_session.query(ImplementationWorkspace).filter(
        ImplementationWorkspace.id.in_(new_ids)
    ).delete(synchronize_session=False)
    db_session.commit()


def test_workspace_creation_seeds_a_plan_and_exposes_progress(
    client, create_test_user, cleanup_implementation_workspaces
):
    manager = create_test_user(
        email="implementation-manager@example.com",
        role=UserRole.ADMINISTRATOR,
    )
    authenticate_client(client, manager)

    response = client.post(
        WORKSPACE_URL,
        json={
            "title": "Northwind bank implementation",
            "description": "Customer onboarding and go-live plan.",
            "start_date": "2026-11-01",
            "target_go_live_date": "2027-01-15",
        },
    )

    assert response.status_code == 201, response.text
    workspace = response.json()["data"]
    assert workspace["title"] == "Northwind bank implementation"
    assert workspace["status"] == "NOT_STARTED"
    assert workspace["progress_percent"] == 0

    detail_response = client.get(f"{WORKSPACE_URL}/{workspace['id']}")
    assert detail_response.status_code == 200, detail_response.text
    detail = detail_response.json()["data"]
    assert len(detail["milestones"]) == 4
    assert len(detail["tasks"]) >= 7
    assert detail["members"][0]["role"] == "MANAGER"


def test_workspace_tasks_can_be_assigned_and_completed(
    client, create_test_user, cleanup_implementation_workspaces
):
    manager = create_test_user(
        email="implementation-task-manager@example.com",
        role=UserRole.ADMINISTRATOR,
    )
    implementer = create_test_user(
        email="implementation-task-owner@example.com",
        role=UserRole.REVIEWER,
    )
    authenticate_client(client, manager)
    create_response = client.post(
        WORKSPACE_URL,
        json={"title": "Assignment workflow test"},
    )
    assert create_response.status_code == 201, create_response.text
    workspace_id = create_response.json()["data"]["id"]

    add_member_response = client.post(
        f"{WORKSPACE_URL}/{workspace_id}/members",
        json={"user_id": str(implementer.id), "role": "MEMBER"},
    )
    assert add_member_response.status_code == 201, add_member_response.text

    create_task_response = client.post(
        f"{WORKSPACE_URL}/{workspace_id}/tasks",
        json={
            "title": "Validate API integration",
            "category": "TECHNICAL",
            "assigned_to": str(implementer.id),
        },
    )
    assert create_task_response.status_code == 201, create_task_response.text
    task_id = create_task_response.json()["data"]["id"]
    assert create_task_response.json()["data"]["assigned_to"] == str(implementer.id)

    authenticate_client(client, implementer)
    update_response = client.patch(
        f"{WORKSPACE_URL}/{workspace_id}/tasks/{task_id}",
        json={"status": "COMPLETED"},
    )
    assert update_response.status_code == 200, update_response.text
    assert update_response.json()["data"]["status"] == "COMPLETED"

    comment_response = client.post(
        f"{WORKSPACE_URL}/{workspace_id}/comments",
        json={
            "body": "API integration has passed the agreed checks.",
            "task_id": task_id,
        },
    )
    assert comment_response.status_code == 201, comment_response.text
    assert "passed the agreed checks" in comment_response.json()["data"]["body"]


def test_workspace_requires_membership_and_stage_advances_sequentially(
    client, create_test_user, cleanup_implementation_workspaces
):
    manager = create_test_user(
        email="implementation-stage-manager@example.com",
        role=UserRole.ADMINISTRATOR,
    )
    outsider = create_test_user(
        email="implementation-workspace-outsider@example.com",
        role=UserRole.ADMINISTRATOR,
    )
    authenticate_client(client, manager)
    create_response = client.post(
        WORKSPACE_URL,
        json={"title": "Protected implementation workspace"},
    )
    assert create_response.status_code == 201, create_response.text
    workspace_id = create_response.json()["data"]["id"]

    skip_stage_response = client.patch(
        f"{WORKSPACE_URL}/{workspace_id}/status",
        json={"status": "INTEGRATION"},
    )
    assert skip_stage_response.status_code == 400

    next_stage_response = client.patch(
        f"{WORKSPACE_URL}/{workspace_id}/status",
        json={"status": "CONFIGURATION"},
    )
    assert next_stage_response.status_code == 200, next_stage_response.text

    authenticate_client(client, outsider)
    forbidden_response = client.get(f"{WORKSPACE_URL}/{workspace_id}")
    assert forbidden_response.status_code == 404
