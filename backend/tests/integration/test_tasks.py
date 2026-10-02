from app.models.notification import Notification
from app.utils.enums import NotificationEventType, UserRole
from tests.helpers import authenticate_client, create_customer_with_data


def test_task_can_be_created(
    client,
    create_test_user,
    cleanup_tasks,
):
    admin = create_test_user(
        email="task-create-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(
        client,
        admin,
    )

    response = client.post(
        "/api/v1/tasks",
        json={
            "title": "Review customer information",
            "description": "Review submitted customer information.",
            "priority": "HIGH",
        },
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["title"] == "Review customer information"
    assert data["description"] == "Review submitted customer information."
    assert data["priority"] == "HIGH"
    assert data["status"] == "NEW"
    assert data["assigned_to"] is None


def test_task_can_be_created_assigned(
    client,
    db_session,
    create_test_user,
    cleanup_tasks,
    cleanup_notifications,
):
    admin = create_test_user(
        email="task-created-assigned-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    reviewer = create_test_user(
        email="task-created-assigned-reviewer@example.com",
        role=UserRole.REVIEWER,
    )

    authenticate_client(
        client,
        admin,
    )

    response = client.post(
        "/api/v1/tasks",
        json={
            "title": "Review verification document",
            "assigned_to": str(reviewer.id),
            "priority": "MEDIUM",
        },
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["assigned_to"] == str(reviewer.id)
    assert data["status"] == "ASSIGNED"

    task_id = data["id"]

    notification = (
        db_session.query(Notification)
        .filter(
            Notification.user_id == reviewer.id,
            Notification.event_type == NotificationEventType.TASK_ASSIGNED,
            Notification.resource_type == "task",
            Notification.resource_id == task_id,
        )
        .order_by(Notification.created_at.desc())
        .first()
    )

    assert notification is not None
    assert notification.title == "New task assigned"
    assert notification.status.value == "UNREAD"
    assert notification.read_at is None


def test_task_can_be_assigned(
    client,
    db_session,
    create_test_user,
    cleanup_tasks,
    cleanup_notifications,
):
    admin = create_test_user(
        email="task-assign-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    reviewer = create_test_user(
        email="task-assign-reviewer@example.com",
        role=UserRole.REVIEWER,
    )

    authenticate_client(
        client,
        admin,
    )

    create_response = client.post(
        "/api/v1/tasks",
        json={
            "title": "Assign this task",
        },
    )

    assert create_response.status_code == 200

    task_id = create_response.json()["data"]["id"]

    response = client.post(
        f"/api/v1/tasks/{task_id}/assign",
        json={
            "assigned_to": str(reviewer.id),
        },
    )

    assert response.status_code == 200

    notification = (
        db_session.query(Notification)
        .filter(
            Notification.user_id == reviewer.id,
            Notification.event_type == NotificationEventType.TASK_ASSIGNED,
            Notification.resource_type == "task",
            Notification.resource_id == task_id,
        )
        .order_by(Notification.created_at.desc())
        .first()
    )

    assert notification is not None
    assert notification.title == "New task assigned"
    assert notification.message == (
        'The task "Assign this task" has been assigned to you.'
    )


def test_user_can_see_their_tasks(
    client,
    create_test_user,
    cleanup_tasks,
):
    admin = create_test_user(
        email="task-my-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    reviewer = create_test_user(
        email="task-my-reviewer@example.com",
        role=UserRole.REVIEWER,
    )

    authenticate_client(
        client,
        admin,
    )

    first_response = client.post(
        "/api/v1/tasks",
        json={
            "title": "Reviewer task",
            "assigned_to": str(reviewer.id),
        },
    )

    second_response = client.post(
        "/api/v1/tasks",
        json={
            "title": "Another task",
        },
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200

    authenticate_client(
        client,
        reviewer,
    )

    response = client.get(
        "/api/v1/tasks/my",
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["total"] == 1
    assert data["tasks"][0]["title"] == "Reviewer task"


def test_task_status_updates_follow_workflow(
    client,
    create_test_user,
    cleanup_tasks,
):
    admin = create_test_user(
        email="task-status-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    reviewer = create_test_user(
        email="task-status-reviewer@example.com",
        role=UserRole.REVIEWER,
    )

    authenticate_client(
        client,
        admin,
    )

    create_response = client.post(
        "/api/v1/tasks",
        json={
            "title": "Status workflow task",
            "assigned_to": str(reviewer.id),
        },
    )

    assert create_response.status_code == 200

    task_id = create_response.json()["data"]["id"]

    authenticate_client(
        client,
        reviewer,
    )

    response = client.patch(
        f"/api/v1/tasks/{task_id}/status",
        json={
            "status": "IN_PROGRESS",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "IN_PROGRESS"

    response = client.post(
        f"/api/v1/tasks/{task_id}/complete",
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "COMPLETED"


def test_task_cannot_skip_status(
    client,
    create_test_user,
    cleanup_tasks,
):
    admin = create_test_user(
        email="task-no-skip-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    reviewer = create_test_user(
        email="task-no-skip-reviewer@example.com",
        role=UserRole.REVIEWER,
    )

    authenticate_client(
        client,
        admin,
    )

    create_response = client.post(
        "/api/v1/tasks",
        json={
            "title": "No status skipping",
            "assigned_to": str(reviewer.id),
        },
    )

    assert create_response.status_code == 200

    task_id = create_response.json()["data"]["id"]

    authenticate_client(
        client,
        reviewer,
    )

    response = client.patch(
        f"/api/v1/tasks/{task_id}/status",
        json={
            "status": "COMPLETED",
        },
    )

    assert response.status_code == 400
    assert response.json()["success"] is False


def test_task_status_history_is_recorded(
    client,
    create_test_user,
    cleanup_tasks,
):
    admin = create_test_user(
        email="task-history-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    reviewer = create_test_user(
        email="task-history-reviewer@example.com",
        role=UserRole.REVIEWER,
    )

    authenticate_client(
        client,
        admin,
    )

    create_response = client.post(
        "/api/v1/tasks",
        json={
            "title": "Task history",
            "assigned_to": str(reviewer.id),
        },
    )

    assert create_response.status_code == 200

    task_id = create_response.json()["data"]["id"]

    authenticate_client(
        client,
        reviewer,
    )

    response = client.patch(
        f"/api/v1/tasks/{task_id}/status",
        json={
            "status": "IN_PROGRESS",
        },
    )

    assert response.status_code == 200

    detail_response = client.get(
        f"/api/v1/tasks/{task_id}",
    )

    assert detail_response.status_code == 200

    history = detail_response.json()["data"]["status_history"]

    assert len(history) == 2

    assert history[0]["from_status"] is None
    assert history[0]["to_status"] == "ASSIGNED"

    assert history[1]["from_status"] == "ASSIGNED"
    assert history[1]["to_status"] == "IN_PROGRESS"


def test_task_comment_can_be_added(
    client,
    create_test_user,
    cleanup_tasks,
):
    admin = create_test_user(
        email="task-comment-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    reviewer = create_test_user(
        email="task-comment-reviewer@example.com",
        role=UserRole.REVIEWER,
    )

    authenticate_client(
        client,
        admin,
    )

    create_response = client.post(
        "/api/v1/tasks",
        json={
            "title": "Task comments",
            "assigned_to": str(reviewer.id),
        },
    )

    assert create_response.status_code == 200

    task_id = create_response.json()["data"]["id"]

    authenticate_client(
        client,
        reviewer,
    )

    response = client.post(
        f"/api/v1/tasks/{task_id}/comments",
        json={
            "comment": "I reviewed the task.",
        },
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["task_id"] == task_id
    assert data["author_id"] == str(reviewer.id)
    assert data["comment"] == "I reviewed the task."


def test_task_can_be_linked_to_workflow_step(
    client,
    create_test_user,
    cleanup_tasks,
    cleanup_test_customers,
    cleanup_workflow_executions,
):
    admin = create_test_user(
        email="task-workflow-admin@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(
        client,
        admin,
    )

    customer = create_customer_with_data(
        client,
        email="onboarding-order@example.com",
    )

    customer_id = customer.json()["data"]["id"]

    start_response = client.post(
        f"/api/v1/customers/{customer_id}/onboarding",
    )

    assert start_response.status_code == 200

    step_response = client.get(
        f"/api/v1/customers/{customer_id}/onboarding",
    )

    assert step_response.status_code == 200

    execution_id = step_response.json()["data"]["id"]
    step_execution_id = step_response.json()["data"]["step_executions"][0]["id"]

    response = client.post(
        "/api/v1/tasks",
        json={
            "title": "Complete workflow step",
            "workflow_execution_id": execution_id,
            "workflow_step_execution_id": step_execution_id,
        },
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["workflow_execution_id"] == execution_id

    assert data["workflow_step_execution_id"] == step_execution_id
