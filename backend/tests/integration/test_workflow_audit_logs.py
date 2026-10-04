import uuid

from app.models.audit_log import AuditLog
from app.services.workflow_service import WorkflowService
from app.utils.enums import (
    AuditEventType,
    UserRole,
    WorkflowExecutionStatus,
    WorkflowStepExecutionStatus,
)
from tests.helpers import authenticate_client


def _create_workflow_with_steps(
    client,
    *,
    step_names: list[str],
):
    """
    Create a workflow, add the requested steps, activate it,
    and return the workflow ID.
    """
    workflow_response = client.post(
        "/api/v1/workflows",
        json={
            "name": f"Workflow Audit Test {uuid.uuid4()}",
            "description": "Workflow audit integration test.",
        },
    )

    assert workflow_response.status_code == 201

    workflow_id = workflow_response.json()["data"]["id"]

    for order_number, step_name in enumerate(
        step_names,
        start=1,
    ):
        response = client.post(
            f"/api/v1/workflows/{workflow_id}/steps",
            json={
                "name": step_name,
                "order_number": order_number,
                "assigned_role": "Administrator",
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

    return workflow_id


def _start_workflow_execution(
    client,
    workflow_id: str,
):
    """
    Start a workflow execution and return the execution ID.
    """
    response = client.post(
        f"/api/v1/workflows/{workflow_id}/executions",
        json={
            "entity_type": "CUSTOMER",
            "entity_id": str(uuid.uuid4()),
            "context": {
                "source": "workflow-audit-test",
            },
        },
    )

    assert response.status_code == 201

    execution = response.json()["data"]

    assert execution["status"] == "IN_PROGRESS"

    return execution["id"]


def _get_audit_history(
    client,
    execution_id: str,
):
    """
    Retrieve workflow audit history through the public API.
    """
    response = client.get(
        f"/api/v1/workflows/executions/{execution_id}/audit-logs",
    )

    assert response.status_code == 200

    body = response.json()

    assert body["success"] is True

    return body["data"]


def test_workflow_execution_records_complete_audit_history(
    client,
    create_test_user,
    cleanup_workflows,
    cleanup_workflow_executions,
    cleanup_workflow_audit_logs,
):
    admin = create_test_user(
        email=f"workflow-audit-admin-{uuid.uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(
        client,
        admin,
    )

    workflow_id = _create_workflow_with_steps(
        client,
        step_names=[
            "Verification Review",
            "Compliance Review",
        ],
    )

    execution_id = _start_workflow_execution(
        client,
        workflow_id,
    )

    response = client.post(
        f"/api/v1/workflows/executions/{execution_id}/advance",
        json={
            "notes": "Verification completed successfully.",
            "result": {
                "verified": True,
            },
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
            "notes": "Compliance review approved.",
            "result": {
                "approved": True,
            },
        },
    )

    assert response.status_code == 200

    execution = response.json()["data"]

    assert execution["status"] == "COMPLETED"
    assert execution["current_step_id"] is None

    history = _get_audit_history(
        client,
        execution_id,
    )

    actions = {item["action"] for item in history}

    assert actions == {
        "WORKFLOW_STARTED",
        "STEP_COMPLETED",
        "STEP_STARTED",
        "WORKFLOW_COMPLETED",
    }

    assert len(history) == 5

    workflow_started = next(
        item for item in history if item["action"] == "WORKFLOW_STARTED"
    )

    assert workflow_started["workflow_id"] == execution_id
    assert workflow_started["step_name"] == "Verification Review"
    assert workflow_started["old_status"] is None
    assert workflow_started["new_status"] == "IN_PROGRESS"
    assert workflow_started["user_id"] == str(admin.id)
    assert workflow_started["comments"] is None
    assert workflow_started["created_at"] is not None

    completed_steps = [item for item in history if item["action"] == "STEP_COMPLETED"]

    assert len(completed_steps) == 2

    first_completed_step = next(
        item for item in completed_steps if item["step_name"] == "Verification Review"
    )

    assert (
        first_completed_step["old_status"]
        == WorkflowStepExecutionStatus.IN_PROGRESS.value
    )
    assert (
        first_completed_step["new_status"]
        == WorkflowStepExecutionStatus.COMPLETED.value
    )
    assert first_completed_step["user_id"] == str(admin.id)
    assert first_completed_step["comments"] == "Verification completed successfully."

    second_completed_step = next(
        item for item in completed_steps if item["step_name"] == "Compliance Review"
    )

    assert (
        second_completed_step["old_status"]
        == WorkflowStepExecutionStatus.IN_PROGRESS.value
    )
    assert (
        second_completed_step["new_status"]
        == WorkflowStepExecutionStatus.COMPLETED.value
    )
    assert second_completed_step["user_id"] == str(admin.id)
    assert second_completed_step["comments"] == "Compliance review approved."

    step_started = next(item for item in history if item["action"] == "STEP_STARTED")

    assert step_started["workflow_id"] == execution_id
    assert step_started["step_name"] == "Compliance Review"
    assert step_started["old_status"] == WorkflowStepExecutionStatus.PENDING.value
    assert step_started["new_status"] == WorkflowStepExecutionStatus.IN_PROGRESS.value
    assert step_started["user_id"] == str(admin.id)
    assert step_started["comments"] is None

    workflow_completed = next(
        item for item in history if item["action"] == "WORKFLOW_COMPLETED"
    )

    assert workflow_completed["workflow_id"] == execution_id
    assert workflow_completed["step_name"] == "Compliance Review"
    assert workflow_completed["old_status"] == WorkflowExecutionStatus.IN_PROGRESS.value
    assert workflow_completed["new_status"] == WorkflowExecutionStatus.COMPLETED.value
    assert workflow_completed["user_id"] == str(admin.id)
    assert workflow_completed["comments"] == "Compliance review approved."


def test_workflow_action_is_recorded_in_global_audit_log(
    client,
    db_session,
    create_test_user,
    cleanup_workflows,
    cleanup_workflow_executions,
    cleanup_workflow_audit_logs,
):
    admin = create_test_user(
        email=f"workflow-global-audit-{uuid.uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(
        client,
        admin,
    )

    workflow_id = _create_workflow_with_steps(
        client,
        step_names=["Review"],
    )

    execution_id = _start_workflow_execution(
        client,
        workflow_id,
    )

    response = client.post(
        f"/api/v1/workflows/executions/{execution_id}/advance",
        json={
            "notes": "Review completed.",
        },
    )

    assert response.status_code == 200

    execution = response.json()["data"]

    assert execution["status"] == "COMPLETED"

    event = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.user_id == admin.id,
            AuditLog.resource_type == "workflow_execution",
            AuditLog.resource_id == uuid.UUID(execution_id),
            AuditLog.event_type == AuditEventType.WORKFLOW_EXECUTION_COMPLETED,
        )
        .first()
    )

    assert event is not None
    assert event.user_id == admin.id
    assert event.email == admin.email
    assert event.resource_type == "workflow_execution"
    assert event.resource_id == uuid.UUID(execution_id)
    assert event.event_type == AuditEventType.WORKFLOW_EXECUTION_COMPLETED


def test_workflow_cancellation_is_audited(
    client,
    create_test_user,
    cleanup_workflows,
    cleanup_workflow_executions,
    cleanup_workflow_audit_logs,
):
    admin = create_test_user(
        email=f"workflow-cancel-audit-{uuid.uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(
        client,
        admin,
    )

    workflow_id = _create_workflow_with_steps(
        client,
        step_names=["Review Step"],
    )

    execution_id = _start_workflow_execution(
        client,
        workflow_id,
    )

    response = client.post(
        f"/api/v1/workflows/executions/{execution_id}/cancel",
        json={
            "notes": "Customer withdrew application.",
        },
    )

    assert response.status_code == 200

    execution = response.json()["data"]

    assert execution["status"] == "CANCELLED"
    assert execution["current_step_id"] is None
    assert execution["step_executions"][0]["status"] == "SKIPPED"

    history = _get_audit_history(
        client,
        execution_id,
    )

    assert len(history) == 3

    skipped = next(item for item in history if item["action"] == "STEP_SKIPPED")

    assert skipped["workflow_id"] == execution_id
    assert skipped["step_name"] == "Review Step"
    assert skipped["old_status"] == WorkflowStepExecutionStatus.IN_PROGRESS.value
    assert skipped["new_status"] == WorkflowStepExecutionStatus.SKIPPED.value
    assert skipped["user_id"] == str(admin.id)
    assert skipped["comments"] == "Customer withdrew application."

    cancelled = next(item for item in history if item["action"] == "WORKFLOW_CANCELLED")

    assert cancelled["workflow_id"] == execution_id
    assert cancelled["step_name"] == "Review Step"
    assert cancelled["old_status"] == WorkflowExecutionStatus.IN_PROGRESS.value
    assert cancelled["new_status"] == WorkflowExecutionStatus.CANCELLED.value
    assert cancelled["user_id"] == str(admin.id)
    assert cancelled["comments"] == "Customer withdrew application."


def test_workflow_failure_is_audited(
    client,
    db_session,
    create_test_user,
    cleanup_workflows,
    cleanup_workflow_executions,
    cleanup_workflow_audit_logs,
):
    admin = create_test_user(
        email=f"workflow-failure-audit-{uuid.uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(
        client,
        admin,
    )

    workflow_id = _create_workflow_with_steps(
        client,
        step_names=["Verification Provider"],
    )

    execution_id = _start_workflow_execution(
        client,
        workflow_id,
    )

    service = WorkflowService(
        db_session,
    )

    execution = service.fail_execution(
        uuid.UUID(execution_id),
        user_id=admin.id,
        email=admin.email,
        actor_role=UserRole.ADMINISTRATOR,
        notes="Verification provider failed.",
    )

    assert execution.status == WorkflowExecutionStatus.FAILED
    assert execution.completed_at is not None

    history = _get_audit_history(
        client,
        execution_id,
    )

    assert len(history) == 3

    step_failed = next(item for item in history if item["action"] == "STEP_FAILED")

    assert step_failed["workflow_id"] == execution_id
    assert step_failed["step_name"] == "Verification Provider"
    assert step_failed["old_status"] == WorkflowStepExecutionStatus.IN_PROGRESS.value
    assert step_failed["new_status"] == WorkflowStepExecutionStatus.FAILED.value
    assert step_failed["user_id"] == str(admin.id)
    assert step_failed["comments"] == "Verification provider failed."

    workflow_failed = next(
        item for item in history if item["action"] == "WORKFLOW_FAILED"
    )

    assert workflow_failed["workflow_id"] == execution_id
    assert workflow_failed["step_name"] == "Verification Provider"
    assert workflow_failed["old_status"] == WorkflowExecutionStatus.IN_PROGRESS.value
    assert workflow_failed["new_status"] == WorkflowExecutionStatus.FAILED.value
    assert workflow_failed["user_id"] == str(admin.id)
    assert workflow_failed["comments"] == "Verification provider failed."


def test_workflow_audit_history_identifies_the_actor(
    client,
    create_test_user,
    cleanup_workflows,
    cleanup_workflow_executions,
    cleanup_workflow_audit_logs,
):
    admin = create_test_user(
        email=f"workflow-actor-audit-{uuid.uuid4()}@example.com",
        role=UserRole.ADMINISTRATOR,
    )

    authenticate_client(
        client,
        admin,
    )

    workflow_id = _create_workflow_with_steps(
        client,
        step_names=["Compliance Review"],
    )

    execution_id = _start_workflow_execution(
        client,
        workflow_id,
    )

    response = client.post(
        f"/api/v1/workflows/executions/{execution_id}/advance",
        json={
            "notes": "Completed by administrator.",
        },
    )

    assert response.status_code == 200

    history = _get_audit_history(
        client,
        execution_id,
    )

    assert history

    for item in history:
        assert item["user_id"] == str(admin.id)

    step_completed = next(
        item for item in history if item["action"] == "STEP_COMPLETED"
    )

    assert step_completed["user_id"] == str(admin.id)
    assert step_completed["created_at"] is not None
