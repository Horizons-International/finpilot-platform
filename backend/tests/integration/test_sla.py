from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.models.notification import Notification
from app.models.task import Task
from app.models.workflow import Workflow, WorkflowExecution
from app.schemas.task import TaskCreate
from app.services.sla_service import SLAService
from app.services.task_service import TaskService
from app.utils.enums import (
    NotificationEventType,
    NotificationStatus,
    SLAStatus,
    TaskStatus,
    UserRole,
    WorkflowExecutionStatus,
)


def test_task_sla_breach_updates_status_and_creates_notification(
    db_session,
    create_test_user,
    cleanup_tasks,
    cleanup_notifications,
):
    user = create_test_user(
        role=UserRole.REVIEWER,
        email=f"sla-task-{uuid4()}@example.com",
    )

    created_at = datetime(
        2026,
        10,
        1,
        10,
        tzinfo=timezone.utc,
    )

    due_date = datetime(
        2026,
        10,
        3,
        10,
        tzinfo=timezone.utc,
    )

    task = Task(
        title="Verification review",
        description="SLA test.",
        assigned_to=user.id,
        priority="MEDIUM",
        status=TaskStatus.ASSIGNED,
        due_date=due_date,
        created_at=created_at,
        sla_status=SLAStatus.WITHIN_SLA,
    )

    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    service = SLAService(db_session)

    service.check_all(
        now=datetime(
            2026,
            10,
            3,
            11,
            tzinfo=timezone.utc,
        )
    )

    db_session.refresh(task)

    assert task.sla_status == SLAStatus.BREACHED

    notification = (
        db_session.query(Notification)
        .filter(
            Notification.user_id == user.id,
            Notification.event_type == NotificationEventType.TASK_SLA_BREACHED.value,
        )
        .first()
    )

    assert notification is not None
    assert notification.status == NotificationStatus.UNREAD


def test_workflow_sla_breach_updates_status_and_notifies_user(
    db_session,
    create_test_tenant,
    create_test_user,
    cleanup_workflows,
    cleanup_notifications,
):
    user = create_test_user(
        role=UserRole.REVIEWER,
        email=f"sla-workflow-{uuid4()}@example.com",
    )

    tenant = create_test_tenant(
        name="Tenant B",
        code=f"TENANT-B-{uuid4().hex[:6].upper()}",
    )

    workflow = Workflow(
        name=f"SLA workflow {uuid4()}",
        description="SLA test workflow.",
        tenant_id=tenant.id,
    )

    db_session.add(workflow)
    db_session.flush()

    started_at = datetime(
        2026,
        10,
        1,
        10,
        tzinfo=timezone.utc,
    )

    due_date = datetime(
        2026,
        10,
        3,
        10,
        tzinfo=timezone.utc,
    )

    execution = WorkflowExecution(
        workflow_id=workflow.id,
        entity_type="customer",
        entity_id=uuid4(),
        status=WorkflowExecutionStatus.IN_PROGRESS,
        started_by=user.id,
        started_at=started_at,
        due_date=due_date,
        sla_status=SLAStatus.WITHIN_SLA,
    )

    db_session.add(execution)
    db_session.commit()
    db_session.refresh(execution)

    service = SLAService(db_session)

    service.check_all(
        now=datetime(
            2026,
            10,
            3,
            11,
            tzinfo=timezone.utc,
        )
    )

    db_session.refresh(execution)

    assert execution.sla_status == SLAStatus.BREACHED

    notification = (
        db_session.query(Notification)
        .filter(
            Notification.user_id == user.id,
            Notification.event_type
            == NotificationEventType.WORKFLOW_SLA_BREACHED.value,
        )
        .first()
    )

    assert notification is not None


def test_completed_task_records_completion_time(
    db_session,
    create_test_user,
    cleanup_tasks,
):
    from datetime import datetime, timedelta, timezone

    from app.utils.enums import SLAStatus, TaskStatus, UserRole

    user = create_test_user(
        role=UserRole.REVIEWER,
        email=f"sla-complete-{uuid4()}@example.com",
    )

    service = TaskService(db_session)

    task = service.create_task(
        TaskCreate(
            title="Complete SLA task",
            assigned_to=user.id,
            due_date=datetime.now(timezone.utc) + timedelta(days=1),
        ),
        user_id=user.id,
        email=user.email,
        role=UserRole.REVIEWER,
    )

    assert task.status == TaskStatus.ASSIGNED

    in_progress = service.update_status(
        task.id,
        TaskStatus.IN_PROGRESS,
        user_id=user.id,
        email=user.email,
        role=UserRole.REVIEWER,
    )

    assert in_progress.status == TaskStatus.IN_PROGRESS

    completed = service.complete_task(
        task.id,
        user_id=user.id,
        email=user.email,
        role=UserRole.REVIEWER,
    )

    assert completed.status == TaskStatus.COMPLETED
    assert completed.completed_at is not None
    assert completed.sla_status == SLAStatus.COMPLETED


def test_sla_notification_is_only_created_on_status_transition(
    db_session,
    create_test_user,
    cleanup_tasks,
    cleanup_notifications,
):
    user = create_test_user(
        role=UserRole.REVIEWER,
        email=f"sla-transition-{uuid4()}@example.com",
    )

    created_at = datetime(
        2026,
        10,
        1,
        10,
        tzinfo=timezone.utc,
    )

    due_date = datetime(
        2026,
        10,
        3,
        10,
        tzinfo=timezone.utc,
    )

    task = Task(
        title="Transition test",
        assigned_to=user.id,
        status=TaskStatus.ASSIGNED,
        due_date=due_date,
        created_at=created_at,
        sla_status=SLAStatus.WITHIN_SLA,
    )

    db_session.add(task)
    db_session.commit()

    service = SLAService(db_session)

    approaching_time = datetime(
        2026,
        10,
        3,
        1,
        tzinfo=timezone.utc,
    )

    service.check_all(
        now=approaching_time,
    )

    service.check_all(
        now=approaching_time + timedelta(minutes=1),
    )

    count = (
        db_session.query(Notification)
        .filter(
            Notification.user_id == user.id,
            Notification.event_type == NotificationEventType.TASK_SLA_APPROACHING.value,
        )
        .count()
    )

    assert count == 1
