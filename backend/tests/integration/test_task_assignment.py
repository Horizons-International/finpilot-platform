import uuid
from typing import Any

from app.models.audit_log import AuditLog
from app.models.notification import Notification
from app.models.task import Task
from app.models.user import User
from app.utils.enums import (
    AuditEventType,
    NotificationEventType,
    TaskAssignmentStrategy,
    TaskStatus,
    UserRole,
    WorkflowStatus,
)
from tests.helpers import authenticate_client


def set_user_department(
    db_session,
    user_id,
    department: str | None,
) -> None:
    user = (
        db_session.query(User)
        .filter(
            User.id == user_id,
        )
        .first()
    )

    assert user is not None

    user.department = department

    db_session.commit()
    db_session.refresh(user)


def create_workflow_execution(
    client,
    *,
    entity_id=None,
    country: str = "SD",
    workflow_name: str | None = None,
    extra_steps: list[dict[str, Any]] | None = None,
):
    if entity_id is None:
        entity_id = uuid.uuid4()

    if workflow_name is None:
        workflow_name = f"Task Assignment Workflow {uuid.uuid4()}"

    workflow_response = client.post(
        "/api/v1/workflows",
        json={
            "name": workflow_name,
            "description": ("Workflow used by task assignment integration tests."),
        },
    )

    assert workflow_response.status_code == 201

    workflow = workflow_response.json()["data"]

    workflow_id = workflow["id"]

    first_step_response = client.post(
        f"/api/v1/workflows/{workflow_id}/steps",
        json={
            "name": "Review Task",
            "order_number": 1,
            "assigned_role": "Reviewer",
        },
    )

    assert first_step_response.status_code == 201

    first_step = first_step_response.json()["data"]

    for step in extra_steps or []:
        step_response = client.post(
            f"/api/v1/workflows/{workflow_id}/steps",
            json=step,
        )

        assert step_response.status_code == 201

    activate_response = client.patch(
        f"/api/v1/workflows/{workflow_id}/status",
        json={
            "status": WorkflowStatus.ACTIVE.value,
        },
    )

    assert activate_response.status_code == 200

    execution_response = client.post(
        f"/api/v1/workflows/{workflow_id}/executions",
        json={
            "entity_type": "customer",
            "entity_id": str(entity_id),
            "context": {
                "source": "task-assignment-test",
                "country": country,
            },
        },
    )

    assert execution_response.status_code == 201

    execution = execution_response.json()["data"]

    first_step_execution = next(
        step_execution
        for step_execution in execution["step_executions"]
        if step_execution["workflow_step_id"] == first_step["id"]
    )

    return {
        "workflow_id": workflow_id,
        "step_id": first_step["id"],
        "execution_id": execution["id"],
        "step_execution_id": first_step_execution["id"],
        "entity_id": str(entity_id),
    }


def create_assignment_rule(
    client,
    *,
    name: str,
    workflow_id: str | None = None,
    workflow_step_id: str | None = None,
    role: str | None = "Reviewer",
    department: str | None = "KYC",
    country: str | None = "SD",
    priority: int = 10,
):
    conditions = {}

    if role is not None:
        conditions["role"] = role

    if department is not None:
        conditions["department"] = department

    if country is not None:
        conditions["country"] = country

    payload = {
        "name": name,
        "description": ("Task assignment rule created by integration tests."),
        "conditions": conditions,
        "strategy": TaskAssignmentStrategy.LEAST_LOADED.value,
        "priority": priority,
    }

    if workflow_id is not None:
        payload["workflow_id"] = workflow_id

    if workflow_step_id is not None:
        payload["workflow_step_id"] = workflow_step_id

    response = client.post(
        "/api/v1/task-assignment-rules",
        json=payload,
    )

    assert response.status_code == 200

    return response.json()["data"]


def activate_assignment_rule(
    client,
    rule_id: str,
):
    response = client.patch(
        f"/api/v1/task-assignment-rules/{rule_id}/status",
        json={
            "is_active": True,
        },
    )

    assert response.status_code == 200

    return response.json()["data"]


def deactivate_assignment_rule(
    client,
    rule_id: str,
):
    response = client.patch(
        f"/api/v1/task-assignment-rules/{rule_id}/status",
        json={
            "is_active": False,
        },
    )

    assert response.status_code == 200

    return response.json()["data"]


def create_workflow_task(
    client,
    *,
    execution_id: str,
    step_execution_id: str,
    title: str = "Workflow task",
):
    response = client.post(
        "/api/v1/tasks",
        json={
            "title": title,
            "workflow_execution_id": execution_id,
            "workflow_step_execution_id": step_execution_id,
        },
    )

    assert response.status_code == 200

    return response.json()["data"]


def test_assignment_rule_can_be_created(
    client,
    create_test_user,
    cleanup_task_assignment_rules,
):
    admin = create_test_user(
        email=f"assignment-rule-create-{uuid.uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(
        client,
        admin,
    )

    response = client.post(
        "/api/v1/task-assignment-rules",
        json={
            "name": f"KYC Reviewers {uuid.uuid4()}",
            "description": "Assign KYC work to KYC reviewers.",
            "conditions": {
                "role": "Reviewer",
                "department": "KYC",
                "country": "SD",
            },
            "strategy": TaskAssignmentStrategy.LEAST_LOADED.value,
            "priority": 10,
        },
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["name"].startswith("KYC Reviewers")
    assert data["description"] == ("Assign KYC work to KYC reviewers.")
    assert data["conditions"]["role"] == "Reviewer"
    assert data["conditions"]["department"] == "KYC"
    assert data["conditions"]["country"] == "SD"
    assert data["strategy"] == TaskAssignmentStrategy.LEAST_LOADED.value
    assert data["priority"] == 10
    assert data["is_active"] is False


def test_assignment_rule_can_be_activated_and_deactivated(
    client,
    create_test_user,
    cleanup_task_assignment_rules,
):
    admin = create_test_user(
        email=f"assignment-rule-status-{uuid.uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(
        client,
        admin,
    )

    rule = create_assignment_rule(
        client,
        name=f"Rule Status {uuid.uuid4()}",
    )

    assert rule["is_active"] is False

    active_rule = activate_assignment_rule(
        client,
        rule["id"],
    )

    assert active_rule["is_active"] is True

    inactive_rule = deactivate_assignment_rule(
        client,
        rule["id"],
    )

    assert inactive_rule["is_active"] is False


def test_active_assignment_rule_can_be_listed(
    client,
    create_test_user,
    cleanup_task_assignment_rules,
):
    admin = create_test_user(
        email=f"assignment-rule-list-{uuid.uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(
        client,
        admin,
    )

    rule = create_assignment_rule(
        client,
        name=f"Rule List {uuid.uuid4()}",
    )

    activate_assignment_rule(
        client,
        rule["id"],
    )

    response = client.get(
        "/api/v1/task-assignment-rules",
        params={
            "is_active": True,
        },
    )

    assert response.status_code == 200

    rules = response.json()["data"]

    matching_rule = next(item for item in rules if item["id"] == rule["id"])

    assert matching_rule["is_active"] is True


def test_assignment_rule_is_not_applied_when_inactive(
    client,
    db_session,
    create_test_user,
    cleanup_task_assignment_rules,
    cleanup_tasks,
    cleanup_workflow_executions,
    cleanup_workflows,
):
    admin = create_test_user(
        email=f"assignment-inactive-admin-{uuid.uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    reviewer = create_test_user(
        email=f"assignment-inactive-reviewer-{uuid.uuid4()}@example.com",
        role=UserRole.REVIEWER,
    )

    set_user_department(
        db_session,
        reviewer.id,
        "KYC",
    )

    authenticate_client(
        client,
        admin,
    )

    workflow = create_workflow_execution(
        client,
        country="SD",
    )

    rule = create_assignment_rule(
        client,
        name=f"Inactive Rule {uuid.uuid4()}",
        workflow_id=workflow["workflow_id"],
        workflow_step_id=workflow["step_id"],
    )

    assert rule["is_active"] is False

    task = create_workflow_task(
        client,
        execution_id=workflow["execution_id"],
        step_execution_id=workflow["step_execution_id"],
        title="Inactive rule task",
    )

    assert task["assigned_to"] is None
    assert task["assignment_rule_id"] is None
    assert task["status"] == TaskStatus.NEW.value


def test_task_is_automatically_assigned_by_active_rule(
    client,
    db_session,
    create_test_user,
    cleanup_task_assignment_rules,
    cleanup_tasks,
    cleanup_workflow_executions,
    cleanup_workflows,
    cleanup_notifications,
):
    admin = create_test_user(
        email=f"assignment-auto-admin-{uuid.uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    reviewer = create_test_user(
        email=f"assignment-auto-reviewer-{uuid.uuid4()}@example.com",
        role=UserRole.REVIEWER,
    )

    set_user_department(
        db_session,
        reviewer.id,
        "KYC",
    )

    authenticate_client(
        client,
        admin,
    )

    workflow = create_workflow_execution(
        client,
        country="SD",
    )

    rule = create_assignment_rule(
        client,
        name=f"Automatic Rule {uuid.uuid4()}",
        workflow_id=workflow["workflow_id"],
        workflow_step_id=workflow["step_id"],
    )

    activate_assignment_rule(
        client,
        rule["id"],
    )

    task = create_workflow_task(
        client,
        execution_id=workflow["execution_id"],
        step_execution_id=workflow["step_execution_id"],
        title="Automatic assignment task",
    )

    assert task["assigned_to"] == str(reviewer.id)
    assert task["assignment_rule_id"] == rule["id"]
    assert task["status"] == TaskStatus.ASSIGNED.value

    notification = (
        db_session.query(Notification)
        .filter(
            Notification.user_id == reviewer.id,
            Notification.event_type == NotificationEventType.TASK_ASSIGNED,
            Notification.resource_type == "task",
            Notification.resource_id == task["id"],
        )
        .order_by(Notification.created_at.desc())
        .first()
    )

    assert notification is not None
    assert notification.title == "New task assigned"
    assert "automatically assigned" in notification.message


def test_assignment_uses_country_condition(
    client,
    db_session,
    create_test_user,
    cleanup_task_assignment_rules,
    cleanup_tasks,
    cleanup_workflow_executions,
    cleanup_workflows,
):
    admin = create_test_user(
        email=f"assignment-country-admin-{uuid.uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    reviewer = create_test_user(
        email=f"assignment-country-reviewer-{uuid.uuid4()}@example.com",
        role=UserRole.REVIEWER,
    )

    set_user_department(
        db_session,
        reviewer.id,
        "KYC",
    )

    authenticate_client(
        client,
        admin,
    )

    workflow = create_workflow_execution(
        client,
        country="GB",
    )

    rule = create_assignment_rule(
        client,
        name=f"Sudan Only Rule {uuid.uuid4()}",
        workflow_id=workflow["workflow_id"],
        workflow_step_id=workflow["step_id"],
        country="SD",
    )

    activate_assignment_rule(
        client,
        rule["id"],
    )

    task = create_workflow_task(
        client,
        execution_id=workflow["execution_id"],
        step_execution_id=workflow["step_execution_id"],
        title="Country mismatch task",
    )

    assert task["assigned_to"] is None
    assert task["assignment_rule_id"] is None
    assert task["status"] == TaskStatus.NEW.value


def test_assignment_uses_department_condition(
    client,
    db_session,
    create_test_user,
    cleanup_task_assignment_rules,
    cleanup_tasks,
    cleanup_workflow_executions,
    cleanup_workflows,
):
    admin = create_test_user(
        email=f"assignment-department-admin-{uuid.uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    reviewer = create_test_user(
        email=f"assignment-department-reviewer-{uuid.uuid4()}@example.com",
        role=UserRole.REVIEWER,
    )

    set_user_department(
        db_session,
        reviewer.id,
        "Compliance",
    )

    authenticate_client(
        client,
        admin,
    )

    workflow = create_workflow_execution(
        client,
        country="SD",
    )

    rule = create_assignment_rule(
        client,
        name=f"KYC Department Rule {uuid.uuid4()}",
        workflow_id=workflow["workflow_id"],
        workflow_step_id=workflow["step_id"],
        department="KYC",
    )

    activate_assignment_rule(
        client,
        rule["id"],
    )

    task = create_workflow_task(
        client,
        execution_id=workflow["execution_id"],
        step_execution_id=workflow["step_execution_id"],
        title="Department mismatch task",
    )

    assert task["assigned_to"] is None
    assert task["assignment_rule_id"] is None
    assert task["status"] == TaskStatus.NEW.value


def test_assignment_uses_workflow_step_scope(
    client,
    db_session,
    create_test_user,
    cleanup_task_assignment_rules,
    cleanup_tasks,
    cleanup_workflow_executions,
    cleanup_workflows,
):
    admin = create_test_user(
        email=f"assignment-step-admin-{uuid.uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    reviewer = create_test_user(
        email=f"assignment-step-reviewer-{uuid.uuid4()}@example.com",
        role=UserRole.REVIEWER,
    )

    set_user_department(
        db_session,
        reviewer.id,
        "KYC",
    )

    authenticate_client(
        client,
        admin,
    )

    workflow = create_workflow_execution(
        client,
        country="SD",
        extra_steps=[
            {
                "name": "Second Review Task",
                "order_number": 2,
                "assigned_role": "Reviewer",
            },
        ],
    )

    workflow_response = client.get(
        f"/api/v1/workflows/{workflow['workflow_id']}",
    )

    assert workflow_response.status_code == 200

    workflow_data = workflow_response.json()["data"]

    second_step = next(
        step for step in workflow_data["steps"] if step["order_number"] == 2
    )

    rule = create_assignment_rule(
        client,
        name=f"Wrong Step Rule {uuid.uuid4()}",
        workflow_id=workflow["workflow_id"],
        workflow_step_id=second_step["id"],
    )

    activate_assignment_rule(
        client,
        rule["id"],
    )

    task = create_workflow_task(
        client,
        execution_id=workflow["execution_id"],
        step_execution_id=workflow["step_execution_id"],
        title="Wrong step scope task",
    )

    assert task["assigned_to"] is None
    assert task["assignment_rule_id"] is None
    assert task["status"] == TaskStatus.NEW.value


def test_assignment_uses_least_loaded_user(
    client,
    db_session,
    create_test_user,
    cleanup_task_assignment_rules,
    cleanup_tasks,
    cleanup_workflow_executions,
    cleanup_workflows,
):
    admin = create_test_user(
        email=f"assignment-workload-admin-{uuid.uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    reviewer_one = create_test_user(
        email=f"assignment-workload-one-{uuid.uuid4()}@example.com",
        role=UserRole.REVIEWER,
    )

    reviewer_two = create_test_user(
        email=f"assignment-workload-two-{uuid.uuid4()}@example.com",
        role=UserRole.REVIEWER,
    )

    set_user_department(
        db_session,
        reviewer_one.id,
        "KYC",
    )

    set_user_department(
        db_session,
        reviewer_two.id,
        "KYC",
    )

    authenticate_client(
        client,
        admin,
    )

    workflow = create_workflow_execution(
        client,
        country="SD",
    )

    rule = create_assignment_rule(
        client,
        name=f"Workload Rule {uuid.uuid4()}",
        workflow_id=workflow["workflow_id"],
        workflow_step_id=workflow["step_id"],
    )

    activate_assignment_rule(
        client,
        rule["id"],
    )

    first_task_response = client.post(
        "/api/v1/tasks",
        json={
            "title": "Existing reviewer workload",
            "assigned_to": str(reviewer_one.id),
            "workflow_execution_id": workflow["execution_id"],
            "workflow_step_execution_id": workflow["step_execution_id"],
        },
    )

    assert first_task_response.status_code == 200

    first_task = first_task_response.json()["data"]

    assert first_task["assigned_to"] == str(reviewer_one.id)
    assert first_task["status"] == TaskStatus.ASSIGNED.value

    second_task = create_workflow_task(
        client,
        execution_id=workflow["execution_id"],
        step_execution_id=workflow["step_execution_id"],
        title="Least loaded task",
    )

    assert second_task["assigned_to"] == str(reviewer_two.id)
    assert second_task["assignment_rule_id"] == rule["id"]
    assert second_task["status"] == TaskStatus.ASSIGNED.value


def test_completed_tasks_do_not_count_toward_workload(
    client,
    db_session,
    create_test_user,
    cleanup_task_assignment_rules,
    cleanup_tasks,
    cleanup_workflow_executions,
    cleanup_workflows,
):
    admin = create_test_user(
        email=f"assignment-completed-admin-{uuid.uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    reviewer_one = create_test_user(
        email=f"assignment-completed-one-{uuid.uuid4()}@example.com",
        role=UserRole.REVIEWER,
    )

    reviewer_two = create_test_user(
        email=f"assignment-completed-two-{uuid.uuid4()}@example.com",
        role=UserRole.REVIEWER,
    )

    set_user_department(
        db_session,
        reviewer_one.id,
        "KYC",
    )

    set_user_department(
        db_session,
        reviewer_two.id,
        "KYC",
    )

    authenticate_client(
        client,
        admin,
    )

    workflow = create_workflow_execution(
        client,
        country="SD",
    )

    rule = create_assignment_rule(
        client,
        name=f"Completed Workload Rule {uuid.uuid4()}",
        workflow_id=workflow["workflow_id"],
        workflow_step_id=workflow["step_id"],
    )

    activate_assignment_rule(
        client,
        rule["id"],
    )

    existing_task_response = client.post(
        "/api/v1/tasks",
        json={
            "title": "Completed workload task",
            "assigned_to": str(reviewer_one.id),
            "workflow_execution_id": workflow["execution_id"],
            "workflow_step_execution_id": workflow["step_execution_id"],
        },
    )

    assert existing_task_response.status_code == 200

    existing_task_id = existing_task_response.json()["data"]["id"]

    authenticate_client(
        client,
        reviewer_one,
    )

    status_response = client.patch(
        f"/api/v1/tasks/{existing_task_id}/status",
        json={
            "status": TaskStatus.IN_PROGRESS.value,
        },
    )

    assert status_response.status_code == 200

    complete_response = client.post(
        f"/api/v1/tasks/{existing_task_id}/complete",
    )

    assert complete_response.status_code == 200
    assert complete_response.json()["data"]["status"] == TaskStatus.COMPLETED.value

    authenticate_client(
        client,
        admin,
    )

    auto_assigned_task = create_workflow_task(
        client,
        execution_id=workflow["execution_id"],
        step_execution_id=workflow["step_execution_id"],
        title="Workload ignores completed task",
    )

    assert auto_assigned_task["assignment_rule_id"] == rule["id"]


def test_assignment_rule_requires_matching_role(
    client,
    db_session,
    create_test_user,
    cleanup_task_assignment_rules,
    cleanup_tasks,
    cleanup_workflow_executions,
    cleanup_workflows,
):
    admin = create_test_user(
        email=f"assignment-role-admin-{uuid.uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    reviewer = create_test_user(
        email=f"assignment-role-reviewer-{uuid.uuid4()}@example.com",
        role=UserRole.REVIEWER,
    )

    set_user_department(
        db_session,
        reviewer.id,
        "KYC",
    )

    authenticate_client(
        client,
        admin,
    )

    workflow = create_workflow_execution(
        client,
        country="SD",
    )

    response = client.post(
        "/api/v1/task-assignment-rules",
        json={
            "name": f"Compliance Role Rule {uuid.uuid4()}",
            "workflow_id": workflow["workflow_id"],
            "workflow_step_id": workflow["step_id"],
            "conditions": {
                "role": UserRole.COMPLIANCE_OFFICER.value,
                "department": "KYC",
                "country": "SD",
            },
            "strategy": (TaskAssignmentStrategy.LEAST_LOADED.value),
            "priority": 10,
        },
    )

    assert response.status_code == 400

    data = response.json()

    assert data["success"] is False


def test_higher_priority_rule_is_applied_first(
    client,
    db_session,
    create_test_user,
    cleanup_task_assignment_rules,
    cleanup_tasks,
    cleanup_workflow_executions,
    cleanup_workflows,
):
    admin = create_test_user(
        email=f"assignment-priority-admin-{uuid.uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    reviewer = create_test_user(
        email=f"assignment-priority-reviewer-{uuid.uuid4()}@example.com",
        role=UserRole.REVIEWER,
    )

    set_user_department(
        db_session,
        reviewer.id,
        "KYC",
    )

    authenticate_client(
        client,
        admin,
    )

    workflow = create_workflow_execution(
        client,
        country="SD",
    )

    low_priority_rule = create_assignment_rule(
        client,
        name=f"Low Priority Rule {uuid.uuid4()}",
        workflow_id=workflow["workflow_id"],
        workflow_step_id=workflow["step_id"],
        priority=100,
    )

    high_priority_rule = create_assignment_rule(
        client,
        name=f"High Priority Rule {uuid.uuid4()}",
        workflow_id=workflow["workflow_id"],
        workflow_step_id=workflow["step_id"],
        priority=10,
    )

    activate_assignment_rule(
        client,
        low_priority_rule["id"],
    )

    activate_assignment_rule(
        client,
        high_priority_rule["id"],
    )

    task = create_workflow_task(
        client,
        execution_id=workflow["execution_id"],
        step_execution_id=workflow["step_execution_id"],
        title="Priority rule task",
    )

    assert task["assigned_to"] == str(reviewer.id)
    assert task["assignment_rule_id"] == high_priority_rule["id"]


def test_automatic_assignment_is_audited(
    client,
    db_session,
    create_test_user,
    cleanup_task_assignment_rules,
    cleanup_tasks,
    cleanup_workflow_executions,
    cleanup_workflows,
):
    admin = create_test_user(
        email=f"assignment-audit-admin-{uuid.uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    reviewer = create_test_user(
        email=f"assignment-audit-reviewer-{uuid.uuid4()}@example.com",
        role=UserRole.REVIEWER,
    )

    set_user_department(
        db_session,
        reviewer.id,
        "KYC",
    )

    authenticate_client(
        client,
        admin,
    )

    workflow = create_workflow_execution(
        client,
        country="SD",
    )

    rule = create_assignment_rule(
        client,
        name=f"Audit Rule {uuid.uuid4()}",
        workflow_id=workflow["workflow_id"],
        workflow_step_id=workflow["step_id"],
    )

    activate_assignment_rule(
        client,
        rule["id"],
    )

    task = create_workflow_task(
        client,
        execution_id=workflow["execution_id"],
        step_execution_id=workflow["step_execution_id"],
        title="Audited assignment task",
    )

    assignment_audit = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.event_type == AuditEventType.TASK_AUTO_ASSIGNED,
            AuditLog.resource_type == "task",
            AuditLog.resource_id == uuid.UUID(task["id"]),
        )
        .order_by(
            AuditLog.timestamp.desc(),
        )
        .first()
    )

    assert assignment_audit is not None

    rule_audit = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.event_type == AuditEventType.TASK_ASSIGNMENT_RULE_APPLIED,
            AuditLog.resource_type == "task_assignment_rule",
            AuditLog.resource_id == uuid.UUID(rule["id"]),
        )
        .order_by(
            AuditLog.timestamp.desc(),
        )
        .first()
    )

    assert rule_audit is not None

    saved_task = (
        db_session.query(Task)
        .filter(
            Task.id == uuid.UUID(task["id"]),
        )
        .first()
    )

    assert saved_task is not None
    assert saved_task.assigned_to == reviewer.id
    assert saved_task.assignment_rule_id == uuid.UUID(rule["id"])


def test_assignment_rule_cannot_be_updated_while_active(
    client,
    create_test_user,
    cleanup_task_assignment_rules,
):
    admin = create_test_user(
        email=f"assignment-rule-update-admin-{uuid.uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(
        client,
        admin,
    )

    rule = create_assignment_rule(
        client,
        name=f"Active Update Rule {uuid.uuid4()}",
    )

    activate_assignment_rule(
        client,
        rule["id"],
    )

    response = client.put(
        f"/api/v1/task-assignment-rules/{rule['id']}",
        json={
            "description": "This update should fail.",
        },
    )

    assert response.status_code == 400

    data = response.json()

    assert data["success"] is False


def test_deactivated_rule_is_no_longer_applied(
    client,
    db_session,
    create_test_user,
    cleanup_task_assignment_rules,
    cleanup_tasks,
    cleanup_workflow_executions,
    cleanup_workflows,
):
    admin = create_test_user(
        email=f"assignment-deactivated-admin-{uuid.uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    reviewer = create_test_user(
        email=f"assignment-deactivated-reviewer-{uuid.uuid4()}@example.com",
        role=UserRole.REVIEWER,
    )

    set_user_department(
        db_session,
        reviewer.id,
        "KYC",
    )

    authenticate_client(
        client,
        admin,
    )

    workflow = create_workflow_execution(
        client,
        country="SD",
    )

    rule = create_assignment_rule(
        client,
        name=f"Deactivate Rule {uuid.uuid4()}",
        workflow_id=workflow["workflow_id"],
        workflow_step_id=workflow["step_id"],
    )

    activate_assignment_rule(
        client,
        rule["id"],
    )

    first_task = create_workflow_task(
        client,
        execution_id=workflow["execution_id"],
        step_execution_id=workflow["step_execution_id"],
        title="First automatically assigned task",
    )

    assert first_task["assigned_to"] == str(reviewer.id)

    deactivate_assignment_rule(
        client,
        rule["id"],
    )

    second_task = create_workflow_task(
        client,
        execution_id=workflow["execution_id"],
        step_execution_id=workflow["step_execution_id"],
        title="Second unassigned task",
    )

    assert second_task["assigned_to"] is None
    assert second_task["assignment_rule_id"] is None
    assert second_task["status"] == TaskStatus.NEW.value
