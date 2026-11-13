"""Native-async task lifecycle, assignment, SLA, comments and audit handling."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.task import Task, TaskComment
from app.models.task_assignment_rule import TaskAssignmentRule
from app.models.user import User
from app.models.workflow import Workflow, WorkflowExecution, WorkflowStepExecution
from app.repositories.async_task_repository import AsyncTaskRepository
from app.schemas.task import (
    TaskCommentCreate,
    TaskCreate,
    TaskListResponse,
    TaskResponse,
    TaskUpdate,
)
from app.services.async_audit_service import AsyncAuditService
from app.services.async_notification_service import AsyncNotificationService
from app.services.async_tenant_access_audit import deny_tenant_access
from app.services.sla_service import SLAService
from app.utils.date_time import to_utc, utc_now
from app.utils.enums import (
    AuditEventType,
    NotificationEventType,
    SLAStatus,
    TaskAssignmentStrategy,
    TaskPriority,
    TaskStatus,
    UserRole,
    UserStatus,
    WorkflowExecutionStatus,
)
from app.utils.errors import bad_request, forbidden, not_found
from app.utils.pagination import validate_pagination

TASK_STATUS_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.NEW: {TaskStatus.ASSIGNED, TaskStatus.CANCELLED},
    TaskStatus.ASSIGNED: {TaskStatus.IN_PROGRESS, TaskStatus.CANCELLED},
    TaskStatus.IN_PROGRESS: {TaskStatus.COMPLETED, TaskStatus.CANCELLED},
    TaskStatus.COMPLETED: set(),
    TaskStatus.CANCELLED: set(),
}
_ACTIVE_TASK_STATUSES = (TaskStatus.NEW, TaskStatus.ASSIGNED, TaskStatus.IN_PROGRESS)


class AsyncTaskService:
    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        existing_tenant = db.info.get("tenant_id")
        if existing_tenant is not None and existing_tenant != tenant_id:
            raise ValueError("Task service tenant does not match session tenant.")
        db.info["tenant_id"] = tenant_id
        self.db = db
        self.tenant_id = tenant_id
        self.repository = AsyncTaskRepository(db, tenant_id)
        self.audit = AsyncAuditService(db)
        self.notifications = AsyncNotificationService(db, tenant_id)

    async def _get_task(self, task_id: UUID, *, for_update: bool = False) -> Task:
        task = (
            await self.repository.get_by_id_for_update(task_id)
            if for_update
            else await self.repository.get_by_id(task_id)
        )
        if task is None:
            await deny_tenant_access(
                self.db, resource_type="task", resource_id=task_id, resource_name="Task"
            )
        return task

    async def _active_user(self, user_id: UUID) -> User:
        user = await self.db.scalar(
            select(User).where(User.id == user_id, User.tenant_id == self.tenant_id)
        )
        if user is None:
            await deny_tenant_access(
                self.db,
                resource_type="user",
                resource_id=user_id,
                resource_name="Assigned user",
            )
        if user.is_deleted:
            raise bad_request("The assigned user has been deleted.")
        if user.status != UserStatus.ACTIVE:
            raise bad_request("The assigned user is not active.")
        return user

    @staticmethod
    def _validate_actor(task: Task, *, user_id: UUID, role: UserRole) -> None:
        if role in {UserRole.ADMINISTRATOR, UserRole.COMPLIANCE_OFFICER}:
            return
        if task.assigned_to == user_id:
            return
        raise forbidden("You do not have permission to modify this task.")

    async def _validate_workflow_link(
        self,
        execution_id: UUID | None,
        step_execution_id: UUID | None,
    ) -> None:
        if execution_id is None and step_execution_id is None:
            return
        if execution_id is None or step_execution_id is None:
            raise bad_request(
                "workflow_execution_id and workflow_step_execution_id "
                "must be provided together."
            )
        execution = await self.db.scalar(
            select(WorkflowExecution)
            .join(Workflow, Workflow.id == WorkflowExecution.workflow_id)
            .where(
                WorkflowExecution.id == execution_id,
                WorkflowExecution.tenant_id == self.tenant_id,
                Workflow.tenant_id == self.tenant_id,
            )
        )
        if execution is None:
            raise not_found("Workflow execution")
        if execution.status in {
            WorkflowExecutionStatus.COMPLETED,
            WorkflowExecutionStatus.CANCELLED,
        }:
            raise bad_request(
                "Cannot create a task for a completed or cancelled workflow execution."
            )
        step_execution = await self.db.scalar(
            select(WorkflowStepExecution)
            .join(
                WorkflowExecution,
                WorkflowExecution.id == WorkflowStepExecution.workflow_execution_id,
            )
            .join(Workflow, Workflow.id == WorkflowExecution.workflow_id)
            .where(
                WorkflowStepExecution.id == step_execution_id,
                WorkflowStepExecution.tenant_id == self.tenant_id,
                WorkflowExecution.tenant_id == self.tenant_id,
                Workflow.tenant_id == self.tenant_id,
            )
        )
        if step_execution is None:
            raise not_found("Workflow step execution")
        if step_execution.workflow_execution_id != execution_id:
            raise bad_request(
                "Workflow step execution does not belong "
                "to the specified workflow execution."
            )

    async def _record_status(
        self,
        task: Task,
        *,
        old_status: TaskStatus | None,
        new_status: TaskStatus,
        user_id: UUID,
    ) -> None:
        await self.repository.add_status_history(
            task_id=task.id,
            changed_by=user_id,
            from_status=old_status,
            to_status=new_status,
        )

    async def _evaluate_sla(self, task: Task, *, now: datetime | None = None) -> bool:
        if task.tenant_id != self.tenant_id:
            raise ValueError("Cannot evaluate a task from another tenant.")
        current = now or utc_now()
        new_status = SLAService.calculate_status(
            created_at=task.created_at,
            due_date=task.due_date,
            completed_at=task.completed_at,
            now=current,
        )
        if task.sla_status == new_status:
            return False
        previous = task.sla_status
        task.sla_status = new_status
        if task.assigned_to is not None:
            if (
                new_status == SLAStatus.APPROACHING_DEADLINE
                and previous != SLAStatus.APPROACHING_DEADLINE
            ):
                await self.notifications.create_notification(
                    user_id=task.assigned_to,
                    title="Task approaching SLA deadline",
                    message=f'The task "{task.title}" is approaching its SLA deadline.',
                    event_type=NotificationEventType.TASK_SLA_APPROACHING,
                    resource_type="task",
                    resource_id=task.id,
                )
            elif new_status == SLAStatus.BREACHED and previous != SLAStatus.BREACHED:
                await self.notifications.create_notification(
                    user_id=task.assigned_to,
                    title="Task SLA breached",
                    message=f'The task "{task.title}" has breached its SLA deadline.',
                    event_type=NotificationEventType.TASK_SLA_BREACHED,
                    resource_type="task",
                    resource_id=task.id,
                )
        return True

    async def _auto_assign(
        self,
        task: Task,
        *,
        user_id: UUID,
        email: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> User | None:
        if (
            task.assigned_to is not None
            or task.workflow_execution_id is None
            or task.workflow_step_execution_id is None
        ):
            return None
        execution = await self.db.scalar(
            select(WorkflowExecution).where(
                WorkflowExecution.id == task.workflow_execution_id,
                WorkflowExecution.tenant_id == self.tenant_id,
            )
        )
        step_execution = await self.db.scalar(
            select(WorkflowStepExecution).where(
                WorkflowStepExecution.id == task.workflow_step_execution_id,
                WorkflowStepExecution.tenant_id == self.tenant_id,
            )
        )
        if execution is None:
            raise not_found("Workflow execution")
        if step_execution is None:
            raise not_found("Workflow step execution")
        if step_execution.workflow_execution_id != execution.id:
            raise bad_request(
                "Workflow step execution does not belong to the workflow execution."
            )

        context = execution.context or {}
        country = context.get("country") or context.get("country_of_residence")
        if not country and execution.entity_type.lower() == "customer":
            country = await self.db.scalar(
                select(Customer.country_of_residence).where(
                    Customer.id == execution.entity_id,
                    Customer.tenant_id == self.tenant_id,
                )
            )
        country = str(country).strip().upper() if country else None

        rules_result = await self.db.scalars(
            select(TaskAssignmentRule).where(
                TaskAssignmentRule.tenant_id == self.tenant_id,
                TaskAssignmentRule.is_active.is_(True),
            )
        )
        rules = list(rules_result.all())

        def rank(rule: TaskAssignmentRule) -> tuple[int, int, datetime, str]:
            scope = (
                2
                if rule.workflow_step_id == step_execution.workflow_step_id
                else (1 if rule.workflow_id == execution.workflow_id else 0)
            )
            return (-scope, -len(rule.conditions or {}), rule.created_at, str(rule.id))

        rules.sort(key=lambda rule: (rule.priority, *rank(rule)))
        for rule in rules:
            if (
                rule.workflow_step_id is not None
                and rule.workflow_step_id != step_execution.workflow_step_id
            ):
                continue
            conditions = rule.conditions or {}
            requested_country = conditions.get("country")
            if requested_country is not None and (
                country is None or country != str(requested_country).upper()
            ):
                continue
            requested_role = conditions.get("role")
            if (
                requested_role is not None
                and requested_role != step_execution.assigned_role
            ):
                continue
            role_value = requested_role or step_execution.assigned_role
            candidate_stmt = select(User).where(
                User.tenant_id == self.tenant_id,
                User.status == UserStatus.ACTIVE,
                User.is_deleted.is_(False),
                User.role == role_value,
            )
            if conditions.get("department") is not None:
                candidate_stmt = candidate_stmt.where(
                    User.department == conditions["department"]
                )
            candidate_result = await self.db.scalars(
                candidate_stmt.order_by(User.id.asc()).with_for_update()
            )
            candidates = list(candidate_result.all())
            if not candidates:
                continue
            if rule.strategy != TaskAssignmentStrategy.LEAST_LOADED:
                raise bad_request("Unsupported task assignment strategy.")
            best_user: User | None = None
            best_load: int | None = None
            for candidate in candidates:
                load = int(
                    await self.db.scalar(
                        select(func.count(Task.id)).where(
                            Task.tenant_id == self.tenant_id,
                            Task.assigned_to == candidate.id,
                            Task.status.in_(_ACTIVE_TASK_STATUSES),
                        )
                    )
                    or 0
                )
                if (
                    best_load is None
                    or load < best_load
                    or (
                        load == best_load
                        and str(candidate.id) < str(best_user.id if best_user else "")
                    )
                ):
                    best_user, best_load = candidate, load
            if best_user is None:
                continue
            old_status = task.status
            task.assigned_to = best_user.id
            task.assignment_rule_id = rule.id
            if old_status == TaskStatus.NEW:
                task.status = TaskStatus.ASSIGNED
                await self._record_status(
                    task,
                    old_status=old_status,
                    new_status=TaskStatus.ASSIGNED,
                    user_id=user_id,
                )
            await self.notifications.create_notification(
                user_id=best_user.id,
                title="New task assigned",
                message=(
                    f'The task "{task.title}" has been automatically assigned to you.'
                ),
                event_type=NotificationEventType.TASK_ASSIGNED,
                resource_type="task",
                resource_id=task.id,
            )
            await self.audit.log_event(
                event_type=AuditEventType.TASK_ASSIGNMENT_RULE_APPLIED,
                user_id=user_id,
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
                resource_type="task_assignment_rule",
                resource_id=rule.id,
            )
            await self.audit.log_event(
                event_type=AuditEventType.TASK_AUTO_ASSIGNED,
                user_id=user_id,
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
                resource_type="task",
                resource_id=task.id,
            )
            return best_user
        return None

    async def create_task(
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
            raise forbidden("You do not have permission to create tasks.")
        title = data.title.strip()
        if not title:
            raise bad_request("Task title is required.")
        await self._validate_workflow_link(
            data.workflow_execution_id, data.workflow_step_execution_id
        )
        if data.assigned_to is not None:
            await self._active_user(data.assigned_to)
        initial_status = (
            TaskStatus.ASSIGNED if data.assigned_to is not None else TaskStatus.NEW
        )
        due_date = to_utc(data.due_date) if data.due_date is not None else None
        now = utc_now()
        task = Task(
            tenant_id=self.tenant_id,
            title=title,
            description=data.description,
            assigned_to=data.assigned_to,
            priority=data.priority,
            status=initial_status,
            due_date=due_date,
            completed_at=None,
            sla_status=SLAService.calculate_status(
                created_at=now, due_date=due_date, now=now
            ),
            workflow_execution_id=data.workflow_execution_id,
            workflow_step_execution_id=data.workflow_step_execution_id,
            assignment_rule_id=None,
        )
        task = await self.repository.create(task)
        await self._record_status(
            task, old_status=None, new_status=initial_status, user_id=user_id
        )
        await self.audit.log_event(
            event_type=AuditEventType.TASK_CREATED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="task",
            resource_id=task.id,
        )
        if data.assigned_to is not None:
            await self.audit.log_event(
                event_type=AuditEventType.TASK_ASSIGNED,
                user_id=user_id,
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
                resource_type="task",
                resource_id=task.id,
            )
            await self.notifications.create_notification(
                user_id=data.assigned_to,
                title="New task assigned",
                message=f'The task "{task.title}" has been assigned to you.',
                event_type=NotificationEventType.TASK_ASSIGNED,
                resource_type="task",
                resource_id=task.id,
            )
        elif (
            data.workflow_execution_id is not None
            and data.workflow_step_execution_id is not None
        ):
            await self._auto_assign(
                task,
                user_id=user_id,
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
            )
        if data.priority != TaskPriority.MEDIUM:
            await self.audit.log_event(
                event_type=AuditEventType.TASK_PRIORITY_CHANGED,
                user_id=user_id,
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
                resource_type="task",
                resource_id=task.id,
            )
        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def get_task(self, task_id: UUID, *, user_id: UUID, role: UserRole) -> Task:
        task = await self._get_task(task_id)
        if (
            role
            not in {
                UserRole.AUDITOR,
                UserRole.ADMINISTRATOR,
                UserRole.COMPLIANCE_OFFICER,
            }
            and task.assigned_to != user_id
        ):
            raise forbidden("You can only access tasks assigned to you.")
        return task

    async def get_task_detail(
        self, task_id: UUID, *, user_id: UUID, role: UserRole
    ) -> Task:
        await self.get_task(task_id, user_id=user_id, role=role)
        task = await self.repository.get_detail(task_id)
        if task is None:
            raise not_found("Task")
        return task

    async def list_tasks(
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
        validate_pagination(page, page_size)
        if role == UserRole.REVIEWER or role not in {
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.AUDITOR,
        }:
            assigned_to = user_id
        tasks, total = await self.repository.list_tasks(
            assigned_to=assigned_to,
            status=status,
            priority=priority,
            page=page,
            page_size=page_size,
        )
        return TaskListResponse(
            tasks=[TaskResponse.model_validate(task) for task in tasks],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=(total + page_size - 1) // page_size if total else 0,
        )

    async def update_task(
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
        task = await self._get_task(task_id, for_update=True)
        self._validate_actor(task, user_id=user_id, role=role)
        if task.status in {TaskStatus.COMPLETED, TaskStatus.CANCELLED}:
            raise bad_request("Completed or cancelled tasks cannot be updated.")
        update_data = data.model_dump(exclude_unset=True)
        if not update_data:
            raise bad_request("No task fields were provided for update.")
        changed = False
        priority_changed = False
        if "title" in update_data:
            title = str(update_data["title"]).strip()
            if not title:
                raise bad_request("Task title is required.")
            if title != task.title:
                task.title = title
                changed = True
        if (
            "description" in update_data
            and update_data["description"] != task.description
        ):
            task.description = update_data["description"]
            changed = True
        if "priority" in update_data and update_data["priority"] != task.priority:
            task.priority = update_data["priority"]
            changed = True
            priority_changed = True
        if "due_date" in update_data:
            due = (
                to_utc(update_data["due_date"])
                if update_data["due_date"] is not None
                else None
            )
            if due != task.due_date:
                task.due_date = due
                await self._evaluate_sla(task)
                changed = True
        if not changed:
            raise bad_request("No task fields were changed.")
        await self.repository.update(task)
        await self.audit.log_event(
            event_type=AuditEventType.TASK_UPDATED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="task",
            resource_id=task.id,
        )
        if priority_changed:
            await self.audit.log_event(
                event_type=AuditEventType.TASK_PRIORITY_CHANGED,
                user_id=user_id,
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
                resource_type="task",
                resource_id=task.id,
            )
        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def assign_task(
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
        if role not in {UserRole.ADMINISTRATOR, UserRole.COMPLIANCE_OFFICER}:
            raise forbidden(
                "Only administrators and compliance officers can assign tasks."
            )
        task = await self._get_task(task_id, for_update=True)
        if task.status in {TaskStatus.COMPLETED, TaskStatus.CANCELLED}:
            raise bad_request("Completed or cancelled tasks cannot be assigned.")
        assignee = await self._active_user(assigned_to)
        if task.assigned_to == assignee.id:
            raise bad_request("Task is already assigned to this user.")
        task.assigned_to = assignee.id
        await self.notifications.create_notification(
            user_id=assignee.id,
            title="New task assigned",
            message=f'The task "{task.title}" has been assigned to you.',
            event_type=NotificationEventType.TASK_ASSIGNED,
            resource_type="task",
            resource_id=task.id,
        )
        if task.status == TaskStatus.NEW:
            old_status = task.status
            task.status = TaskStatus.ASSIGNED
            await self._record_status(
                task,
                old_status=old_status,
                new_status=TaskStatus.ASSIGNED,
                user_id=user_id,
            )
            await self.audit.log_event(
                event_type=AuditEventType.TASK_STATUS_CHANGED,
                user_id=user_id,
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
                resource_type="task",
                resource_id=task.id,
            )
        await self.repository.update(task)
        await self.audit.log_event(
            event_type=AuditEventType.TASK_ASSIGNED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="task",
            resource_id=task.id,
        )
        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def update_status(
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
        task = await self._get_task(task_id, for_update=True)
        self._validate_actor(task, user_id=user_id, role=role)
        old_status = task.status
        if old_status == new_status:
            raise bad_request("Task is already in this status.")
        if new_status not in TASK_STATUS_TRANSITIONS.get(old_status, set()):
            raise bad_request(
                f"Invalid task status transition: "
                f"{old_status.value} -> {new_status.value}."
            )
        now = utc_now()
        task.status = new_status
        if new_status == TaskStatus.COMPLETED:
            task.completed_at = now
            await self._evaluate_sla(task, now=now)
        await self._record_status(
            task, old_status=old_status, new_status=new_status, user_id=user_id
        )
        await self.repository.update(task)
        await self.audit.log_event(
            event_type=AuditEventType.TASK_STATUS_CHANGED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="task",
            resource_id=task.id,
        )
        if new_status == TaskStatus.COMPLETED:
            await self.audit.log_event(
                event_type=AuditEventType.TASK_COMPLETED,
                user_id=user_id,
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
                resource_type="task",
                resource_id=task.id,
            )
        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def complete_task(
        self,
        task_id: UUID,
        *,
        user_id: UUID,
        email: str,
        role: UserRole,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> Task:
        return await self.update_status(
            task_id,
            TaskStatus.COMPLETED,
            user_id=user_id,
            email=email,
            role=role,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    async def add_comment(
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
        task = await self._get_task(task_id)
        self._validate_actor(task, user_id=user_id, role=role)
        comment_text = data.comment.strip()
        if not comment_text:
            raise bad_request("Comment is required.")
        comment = await self.repository.add_comment(
            TaskComment(
                tenant_id=self.tenant_id,
                task_id=task.id,
                author_id=user_id,
                comment=comment_text,
            )
        )
        await self.audit.log_event(
            event_type=AuditEventType.TASK_COMMENT_ADDED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="task",
            resource_id=task.id,
        )
        await self.db.commit()
        await self.db.refresh(comment)
        return comment

    async def get_comments(
        self, task_id: UUID, *, user_id: UUID, role: UserRole
    ) -> list[TaskComment]:
        task = await self.get_task(task_id, user_id=user_id, role=role)
        return await self.repository.get_comments(task.id)
