from uuid import UUID

from sqlalchemy.orm import Session

from app.models.task import Task, TaskComment, TaskStatusHistory
from app.models.user import User
from app.models.workflow import (
    WorkflowExecution,
    WorkflowStepExecution,
)
from app.repositories.task_repository import TaskRepository
from app.schemas.task import (
    TaskCommentCreate,
    TaskCreate,
    TaskListResponse,
    TaskResponse,
    TaskUpdate,
)
from app.services.audit_service import AuditService
from app.services.notification_service import NotificationService
from app.services.sla_service import SLAService
from app.services.task_assignment_service import (
    TaskAssignmentService,
)
from app.utils.date_time import to_utc, utc_now
from app.utils.enums import (
    AuditEventType,
    NotificationChannel,
    NotificationEventType,
    TaskPriority,
    TaskStatus,
    UserRole,
    UserStatus,
    WorkflowExecutionStatus,
)
from app.utils.errors import bad_request, forbidden, not_found
from app.utils.pagination import validate_pagination

TASK_STATUS_TRANSITIONS: dict[
    TaskStatus,
    set[TaskStatus],
] = {
    TaskStatus.NEW: {
        TaskStatus.ASSIGNED,
        TaskStatus.CANCELLED,
    },
    TaskStatus.ASSIGNED: {
        TaskStatus.IN_PROGRESS,
        TaskStatus.CANCELLED,
    },
    TaskStatus.IN_PROGRESS: {
        TaskStatus.COMPLETED,
        TaskStatus.CANCELLED,
    },
    TaskStatus.COMPLETED: set(),
    TaskStatus.CANCELLED: set(),
}


class TaskService:
    def __init__(
        self,
        db: Session,
    ) -> None:
        self.db = db
        self.sla_service = SLAService(db)
        self.repository = TaskRepository(db)
        self.audit_service = AuditService(db)
        self.assignment_service = TaskAssignmentService(db)
        self.notification_service = NotificationService(db)

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    def _get_task(
        self,
        task_id: UUID,
        *,
        for_update: bool = False,
    ) -> Task:
        task = (
            self.repository.get_by_id_for_update(task_id)
            if for_update
            else self.repository.get_by_id(task_id)
        )

        if task is None:
            raise not_found("Task")

        return task

    def _get_active_user(
        self,
        user_id: UUID,
    ) -> User:
        user = (
            self.db.query(User)
            .filter(
                User.id == user_id,
            )
            .first()
        )

        if user is None:
            raise not_found("Assigned user")

        if user.is_deleted:
            raise bad_request(
                "The assigned user has been deleted.",
            )

        if user.status != UserStatus.ACTIVE:
            raise bad_request(
                "The assigned user is not active.",
            )

        return user

    def _validate_task_actor(
        self,
        task: Task,
        *,
        user_id: UUID,
        role: UserRole,
    ) -> None:
        if role in {
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
        }:
            return

        if task.assigned_to == user_id:
            return

        raise forbidden(
            "You do not have permission to modify this task.",
        )

    def _validate_workflow_link(
        self,
        workflow_execution_id: UUID | None,
        workflow_step_execution_id: UUID | None,
    ) -> None:
        if workflow_execution_id is None and workflow_step_execution_id is None:
            return

        if workflow_execution_id is None or workflow_step_execution_id is None:
            raise bad_request(
                "workflow_execution_id and "
                "workflow_step_execution_id must be provided together.",
            )

        execution = (
            self.db.query(WorkflowExecution)
            .filter(
                WorkflowExecution.id == workflow_execution_id,
            )
            .first()
        )

        if execution is None:
            raise not_found("Workflow execution")

        if execution.status in {
            WorkflowExecutionStatus.COMPLETED,
            WorkflowExecutionStatus.CANCELLED,
        }:
            raise bad_request(
                "Cannot create a task for a completed or cancelled workflow execution.",
            )

        step_execution = (
            self.db.query(WorkflowStepExecution)
            .filter(
                WorkflowStepExecution.id == workflow_step_execution_id,
            )
            .first()
        )

        if step_execution is None:
            raise not_found(
                "Workflow step execution",
            )

        if step_execution.workflow_execution_id != workflow_execution_id:
            raise bad_request(
                "Workflow step execution does not belong "
                "to the specified workflow execution.",
            )

    def _record_status_change(
        self,
        *,
        task: Task,
        from_status: TaskStatus | None,
        to_status: TaskStatus,
        changed_by: UUID,
    ) -> None:
        history = TaskStatusHistory(
            task_id=task.id,
            changed_by=changed_by,
            from_status=from_status,
            to_status=to_status,
            changed_at=utc_now(),
        )

        self.db.add(history)
        self.db.flush()

    # ------------------------------------------------------------------
    # Creation
    # ------------------------------------------------------------------

    def create_task(
        self,
        data: TaskCreate,
        *,
        user_id: UUID,
        email: str,
        role: UserRole,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> Task:
        if role not in {
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
        }:
            raise forbidden(
                "You do not have permission to create tasks.",
            )

        title = data.title.strip()

        if not title:
            raise bad_request(
                "Task title is required.",
            )

        self._validate_workflow_link(
            data.workflow_execution_id,
            data.workflow_step_execution_id,
        )

        if data.assigned_to is not None:
            self._get_active_user(
                data.assigned_to,
            )

        initial_status = (
            TaskStatus.ASSIGNED if data.assigned_to is not None else TaskStatus.NEW
        )

        due_date = to_utc(data.due_date) if data.due_date is not None else None

        now = utc_now()

        initial_sla_status = SLAService.calculate_status(
            created_at=now,
            due_date=due_date,
            now=now,
        )

        task = Task(
            title=title,
            description=data.description,
            assigned_to=data.assigned_to,
            priority=data.priority,
            status=initial_status,
            due_date=due_date,
            completed_at=None,
            sla_status=initial_sla_status,
            workflow_execution_id=data.workflow_execution_id,
            workflow_step_execution_id=data.workflow_step_execution_id,
            assignment_rule_id=None,
        )

        self.repository.create(task)

        self._record_status_change(
            task=task,
            from_status=None,
            to_status=initial_status,
            changed_by=user_id,
        )

        self.audit_service.log_event(
            event_type=AuditEventType.TASK_CREATED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="task",
            resource_id=task.id,
        )

        if data.assigned_to is not None:
            self.audit_service.log_event(
                event_type=AuditEventType.TASK_ASSIGNED,
                user_id=user_id,
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
                resource_type="task",
                resource_id=task.id,
            )

            self.notification_service.create_notification(
                user_id=data.assigned_to,
                title="New task assigned",
                message=(f'The task "{task.title}" has been assigned to you.'),
                event_type=NotificationEventType.TASK_ASSIGNED,
                resource_type="task",
                resource_id=task.id,
                channels=(NotificationChannel.IN_APP,),
            )
        elif (
            data.workflow_execution_id is not None
            and data.workflow_step_execution_id is not None
        ):
            self.assignment_service.apply_to_task(
                task,
                user_id=user_id,
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
            )

        if data.priority != TaskPriority.MEDIUM:
            self.audit_service.log_event(
                event_type=AuditEventType.TASK_PRIORITY_CHANGED,
                user_id=user_id,
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
                resource_type="task",
                resource_id=task.id,
            )

        self.db.commit()
        self.db.refresh(task)

        return task

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def get_task(
        self,
        task_id: UUID,
        *,
        user_id: UUID,
        role: UserRole,
    ) -> Task:
        task = self._get_task(task_id)

        if role == UserRole.AUDITOR:
            return task

        if role in {
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
        }:
            return task

        if task.assigned_to != user_id:
            raise forbidden(
                "You can only access tasks assigned to you.",
            )

        return task

    def get_task_detail(
        self,
        task_id: UUID,
        *,
        user_id: UUID,
        role: UserRole,
    ) -> Task:
        task = self.get_task(
            task_id,
            user_id=user_id,
            role=role,
        )

        task.status_history
        task.comments

        return task

    def list_tasks(
        self,
        *,
        user_id: UUID,
        role: UserRole,
        assigned_to: UUID | None = None,
        status: TaskStatus | None = None,
        priority: TaskPriority | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> TaskListResponse:
        validate_pagination(
            page,
            page_size,
        )

        if role == UserRole.REVIEWER:
            assigned_to = user_id

        elif role not in {
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.AUDITOR,
        }:
            assigned_to = user_id

        tasks, total = self.repository.list_tasks(
            assigned_to=assigned_to,
            status=status,
            priority=priority,
            page=page,
            page_size=page_size,
        )

        total_pages = (total + page_size - 1) // page_size if total > 0 else 0

        return TaskListResponse(
            tasks=[TaskResponse.model_validate(task) for task in tasks],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )

    # ------------------------------------------------------------------
    # Task update
    # ------------------------------------------------------------------

    def update_task(
        self,
        task_id: UUID,
        data: TaskUpdate,
        *,
        user_id: UUID,
        email: str,
        role: UserRole,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> Task:
        task = self._get_task(
            task_id,
            for_update=True,
        )

        self._validate_task_actor(
            task,
            user_id=user_id,
            role=role,
        )

        if task.status in {
            TaskStatus.COMPLETED,
            TaskStatus.CANCELLED,
        }:
            raise bad_request(
                "Completed or cancelled tasks cannot be updated.",
            )

        update_data = data.model_dump(
            exclude_unset=True,
        )

        if not update_data:
            raise bad_request(
                "No task fields were provided for update.",
            )

        changed = False
        priority_changed = False

        if "title" in update_data:
            title = str(update_data["title"]).strip()

            if not title:
                raise bad_request(
                    "Task title is required.",
                )

            if title != task.title:
                task.title = title
                changed = True

        if "description" in update_data:
            if update_data["description"] != task.description:
                task.description = update_data["description"]
                changed = True

        if "priority" in update_data:
            new_priority = update_data["priority"]

            if new_priority != task.priority:
                task.priority = new_priority
                changed = True
                priority_changed = True

        if "due_date" in update_data:
            new_due_date = (
                to_utc(update_data["due_date"])
                if update_data["due_date"] is not None
                else None
            )

            if new_due_date != task.due_date:
                task.due_date = new_due_date

                self.sla_service.evaluate_task(
                    task,
                )

                changed = True

        if not changed:
            raise bad_request(
                "No task fields were changed.",
            )

        self.repository.update(task)

        self.audit_service.log_event(
            event_type=AuditEventType.TASK_UPDATED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="task",
            resource_id=task.id,
        )

        if priority_changed:
            self.audit_service.log_event(
                event_type=AuditEventType.TASK_PRIORITY_CHANGED,
                user_id=user_id,
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
                resource_type="task",
                resource_id=task.id,
            )

        self.db.commit()
        self.db.refresh(task)

        return task

    # ------------------------------------------------------------------
    # Assignment
    # ------------------------------------------------------------------

    def assign_task(
        self,
        task_id: UUID,
        assigned_to: UUID,
        *,
        user_id: UUID,
        email: str,
        role: UserRole,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> Task:
        if role not in {
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
        }:
            raise forbidden(
                "Only administrators and compliance officers can assign tasks.",
            )

        task = self._get_task(
            task_id,
            for_update=True,
        )

        if task.status in {
            TaskStatus.COMPLETED,
            TaskStatus.CANCELLED,
        }:
            raise bad_request(
                "Completed or cancelled tasks cannot be assigned.",
            )

        assigned_user = self._get_active_user(
            assigned_to,
        )

        old_assigned_to = task.assigned_to

        if old_assigned_to == assigned_user.id:
            raise bad_request(
                "Task is already assigned to this user.",
            )

        task.assigned_to = assigned_user.id

        self.notification_service.create_notification(
            user_id=assigned_user.id,
            title="New task assigned",
            message=(f'The task "{task.title}" has been assigned to you.'),
            event_type=NotificationEventType.TASK_ASSIGNED,
            resource_type="task",
            resource_id=task.id,
            channels=(NotificationChannel.IN_APP,),
        )

        if task.status == TaskStatus.NEW:
            old_status = task.status
            task.status = TaskStatus.ASSIGNED

            self._record_status_change(
                task=task,
                from_status=old_status,
                to_status=TaskStatus.ASSIGNED,
                changed_by=user_id,
            )

            self.audit_service.log_event(
                event_type=AuditEventType.TASK_STATUS_CHANGED,
                user_id=user_id,
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
                resource_type="task",
                resource_id=task.id,
            )

        self.repository.update(task)

        self.audit_service.log_event(
            event_type=AuditEventType.TASK_ASSIGNED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="task",
            resource_id=task.id,
        )

        self.db.commit()
        self.db.refresh(task)

        return task

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def update_status(
        self,
        task_id: UUID,
        new_status: TaskStatus,
        *,
        user_id: UUID,
        email: str,
        role: UserRole,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> Task:
        task = self._get_task(
            task_id,
            for_update=True,
        )

        self._validate_task_actor(
            task,
            user_id=user_id,
            role=role,
        )

        current_status = task.status

        if current_status == new_status:
            raise bad_request(
                "Task is already in this status.",
            )

        allowed_statuses = TASK_STATUS_TRANSITIONS.get(
            current_status,
            set(),
        )

        if new_status not in allowed_statuses:
            raise bad_request(
                "Invalid task status transition: "
                f"{current_status.value} -> {new_status.value}.",
            )

        task.status = new_status

        now = utc_now()

        task.status = new_status

        if new_status == TaskStatus.COMPLETED:
            task.completed_at = now

            self.sla_service.evaluate_task(
                task,
                now=now,
            )

        self._record_status_change(
            task=task,
            from_status=current_status,
            to_status=new_status,
            changed_by=user_id,
        )

        self.repository.update(task)

        self.audit_service.log_event(
            event_type=AuditEventType.TASK_STATUS_CHANGED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="task",
            resource_id=task.id,
        )

        if new_status == TaskStatus.COMPLETED:
            self.audit_service.log_event(
                event_type=AuditEventType.TASK_COMPLETED,
                user_id=user_id,
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
                resource_type="task",
                resource_id=task.id,
            )

        self.db.commit()
        self.db.refresh(task)

        return task

    def complete_task(
        self,
        task_id: UUID,
        *,
        user_id: UUID,
        email: str,
        role: UserRole,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> Task:
        return self.update_status(
            task_id,
            TaskStatus.COMPLETED,
            user_id=user_id,
            email=email,
            role=role,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    # ------------------------------------------------------------------
    # Comments
    # ------------------------------------------------------------------

    def add_comment(
        self,
        task_id: UUID,
        data: TaskCommentCreate,
        *,
        user_id: UUID,
        email: str,
        role: UserRole,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> TaskComment:
        task = self._get_task(task_id)

        self._validate_task_actor(
            task,
            user_id=user_id,
            role=role,
        )

        comment_text = data.comment.strip()

        if not comment_text:
            raise bad_request(
                "Comment is required.",
            )

        comment = TaskComment(
            task_id=task.id,
            author_id=user_id,
            comment=comment_text,
            created_at=utc_now(),
        )

        self.db.add(comment)
        self.db.flush()
        self.db.refresh(comment)

        self.audit_service.log_event(
            event_type=AuditEventType.TASK_COMMENT_ADDED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="task",
            resource_id=task.id,
        )

        self.db.commit()
        self.db.refresh(comment)

        return comment

    def get_comments(
        self,
        task_id: UUID,
        *,
        user_id: UUID,
        role: UserRole,
    ) -> list[TaskComment]:
        task = self.get_task(
            task_id,
            user_id=user_id,
            role=role,
        )

        return (
            self.db.query(TaskComment)
            .filter(
                TaskComment.task_id == task.id,
            )
            .order_by(
                TaskComment.created_at.asc(),
            )
            .all()
        )
