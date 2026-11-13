"""Native-async workflow definition, execution and audit-log service."""

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workflow import (
    Workflow,
    WorkflowExecution,
    WorkflowStep,
    WorkflowStepExecution,
)
from app.models.workflow_audit_log import WorkflowAuditLog
from app.repositories.async_workflow_repository import (
    AsyncWorkflowAuditLogRepository,
    AsyncWorkflowExecutionRepository,
    AsyncWorkflowRepository,
)
from app.schemas.workflow import (
    WorkflowAdvanceRequest,
    WorkflowCreate,
    WorkflowExecutionCancelRequest,
    WorkflowExecutionCreate,
    WorkflowStepCreate,
    WorkflowStepUpdate,
    WorkflowUpdate,
)
from app.services.async_audit_service import AsyncAuditService
from app.services.async_notification_service import AsyncNotificationService
from app.services.sla_service import SLAService
from app.utils.date_time import to_utc, utc_now
from app.utils.enums import (
    AuditEventType,
    NotificationEventType,
    SLAStatus,
    UserRole,
    WorkflowAuditAction,
    WorkflowExecutionStatus,
    WorkflowStatus,
    WorkflowStepExecutionStatus,
)
from app.utils.errors import bad_request, forbidden, not_found

WORKFLOW_STATUS_TRANSITIONS: dict[WorkflowStatus, set[WorkflowStatus]] = {
    WorkflowStatus.DRAFT: {WorkflowStatus.ACTIVE, WorkflowStatus.INACTIVE},
    WorkflowStatus.ACTIVE: {WorkflowStatus.INACTIVE},
    WorkflowStatus.INACTIVE: {WorkflowStatus.ACTIVE},
}
STEP_TEMPORARY_ORDER_BASE = 1_000_000


class AsyncWorkflowService:
    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        active_tenant = db.info.get("tenant_id")
        if active_tenant is not None and active_tenant != tenant_id:
            raise ValueError("Workflow service tenant does not match session tenant.")
        db.info["tenant_id"] = tenant_id
        self.db = db
        self.tenant_id = tenant_id
        self.repository = AsyncWorkflowRepository(db, tenant_id)
        self.execution_repository = AsyncWorkflowExecutionRepository(db, tenant_id)
        self.workflow_audit_repository = AsyncWorkflowAuditLogRepository(db, tenant_id)
        self.audit = AsyncAuditService(db)
        self.notifications = AsyncNotificationService(db, tenant_id)

    async def _get_editable_workflow(self, workflow_id: UUID) -> Workflow:
        workflow = await self.repository.get_by_id(workflow_id)
        if workflow is None:
            raise not_found("Workflow")
        if workflow.status == WorkflowStatus.ACTIVE:
            raise bad_request(
                "Active workflows cannot be modified. "
                "Deactivate the workflow before modifying it."
            )
        if await self.repository.has_execution(workflow.id):
            raise bad_request(
                "This workflow already has executions and cannot be modified."
            )
        return workflow

    async def _assign_step_orders(self, steps: Sequence[WorkflowStep]) -> None:
        if not steps:
            return
        temporary_base = STEP_TEMPORARY_ORDER_BASE + len(steps)
        for index, step in enumerate(steps, start=1):
            step.order_number = temporary_base + index
        await self.db.flush()
        for index, step in enumerate(steps, start=1):
            step.order_number = index
        await self.db.flush()

    async def _record_workflow_audit(
        self,
        *,
        execution_id: UUID,
        step_name: str | None,
        action: WorkflowAuditAction,
        old_status: str | None,
        new_status: str | None,
        user_id: UUID | None,
        comments: str | None = None,
    ) -> WorkflowAuditLog:
        return await self.workflow_audit_repository.create(
            WorkflowAuditLog(
                tenant_id=self.tenant_id,
                workflow_execution_id=execution_id,
                step_name=step_name,
                action=action.value,
                old_status=old_status,
                new_status=new_status,
                user_id=user_id,
                comments=comments,
            )
        )

    @staticmethod
    def _validate_step_actor(step: WorkflowStep, actor_role: UserRole) -> None:
        if actor_role == UserRole.ADMINISTRATOR:
            return
        if step.assigned_role != actor_role.value:
            raise forbidden("You do not have permission to execute this workflow step.")

    async def _evaluate_workflow_sla(
        self, execution: WorkflowExecution, *, now: datetime | None = None
    ) -> bool:
        if execution.tenant_id != self.tenant_id:
            raise ValueError(
                "Cannot evaluate a workflow execution from another tenant."
            )
        current_time = now or utc_now()
        new_status = SLAService.calculate_status(
            created_at=execution.started_at,
            due_date=execution.due_date,
            completed_at=(
                execution.completed_at
                if execution.status == WorkflowExecutionStatus.COMPLETED
                else None
            ),
            now=current_time,
        )
        previous_status = execution.sla_status
        if previous_status == new_status:
            return False
        execution.sla_status = new_status
        if execution.started_by is not None:
            event_type = None
            title = ""
            message = ""
            if (
                new_status == SLAStatus.APPROACHING_DEADLINE
                and previous_status != SLAStatus.APPROACHING_DEADLINE
            ):
                event_type = NotificationEventType.WORKFLOW_SLA_APPROACHING
                title = "Workflow approaching SLA deadline"
                message = (
                    f"Workflow execution {execution.id} "
                    "is approaching its SLA deadline."
                )
            elif (
                new_status == SLAStatus.BREACHED
                and previous_status != SLAStatus.BREACHED
            ):
                event_type = NotificationEventType.WORKFLOW_SLA_BREACHED
                title = "Workflow SLA breached"
                message = (
                    f"Workflow execution {execution.id} has breached its SLA deadline."
                )
            if event_type is not None:
                await self.notifications.create_notification(
                    user_id=execution.started_by,
                    title=title,
                    message=message,
                    event_type=event_type,
                    resource_type="workflow_execution",
                    resource_id=execution.id,
                )
        return True

    async def create_workflow(
        self,
        data: WorkflowCreate,
        *,
        user_id: UUID,
        email: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> Workflow:
        name = data.name.strip()
        if not name:
            raise bad_request("Workflow name is required.")
        if await self.repository.get_by_name(name) is not None:
            raise bad_request("A workflow with this name already exists.")
        workflow = await self.repository.create(
            Workflow(
                tenant_id=self.tenant_id,
                name=name,
                description=data.description,
                status=WorkflowStatus.DRAFT,
            )
        )
        await self.audit.log_event(
            event_type=AuditEventType.WORKFLOW_CREATED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="workflow",
            resource_id=workflow.id,
        )
        await self.db.commit()
        return await self.repository.get_workflow(workflow.id) or workflow

    async def get_workflow(self, workflow_id: UUID) -> Workflow:
        workflow = await self.repository.get_workflow(workflow_id)
        if workflow is None:
            raise not_found("Workflow")
        return workflow

    async def list_workflows(
        self, *, status: WorkflowStatus | None = None
    ) -> list[Workflow]:
        return await self.repository.get_all(status=status)

    async def update_workflow(
        self,
        workflow_id: UUID,
        data: WorkflowUpdate,
        *,
        user_id: UUID,
        email: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> Workflow:
        workflow = await self._get_editable_workflow(workflow_id)
        values = data.model_dump(exclude_unset=True)
        if not values:
            return await self.get_workflow(workflow_id)
        if "name" in values:
            name = str(values["name"]).strip()
            if not name:
                raise bad_request("Workflow name is required.")
            existing = await self.repository.get_by_name(name)
            if existing is not None and existing.id != workflow.id:
                raise bad_request("A workflow with this name already exists.")
            workflow.name = name
        if "description" in values:
            workflow.description = values["description"]
        await self.repository.update(workflow)
        await self.audit.log_event(
            event_type=AuditEventType.WORKFLOW_UPDATED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="workflow",
            resource_id=workflow.id,
        )
        await self.db.commit()
        return await self.get_workflow(workflow.id)

    async def update_workflow_status(
        self,
        workflow_id: UUID,
        new_status: WorkflowStatus,
        *,
        user_id: UUID,
        email: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> Workflow:
        workflow = await self.repository.get_by_id(workflow_id)
        if workflow is None:
            raise not_found("Workflow")
        if workflow.status == new_status:
            raise bad_request("Workflow is already in this status.")
        if new_status not in WORKFLOW_STATUS_TRANSITIONS.get(workflow.status, set()):
            raise bad_request(
                f"Invalid workflow status transition: "
                f"{workflow.status.value} -> {new_status.value}."
            )
        if new_status == WorkflowStatus.ACTIVE and not await self.repository.get_steps(
            workflow.id
        ):
            raise bad_request(
                "A workflow must contain at least one step before it can be activated."
            )
        workflow.status = new_status
        await self.repository.update(workflow)
        await self.audit.log_event(
            event_type=AuditEventType.WORKFLOW_STATUS_CHANGED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="workflow",
            resource_id=workflow.id,
        )
        await self.db.commit()
        return await self.get_workflow(workflow.id)

    async def add_step(
        self,
        workflow_id: UUID,
        data: WorkflowStepCreate,
        *,
        user_id: UUID,
        email: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> WorkflowStep:
        workflow = await self._get_editable_workflow(workflow_id)
        steps = await self.repository.get_steps(workflow.id, for_update=True)
        next_order = len(steps) + 1
        if data.order_number > next_order:
            raise bad_request(f"Step order_number cannot be greater than {next_order}.")
        name = data.name.strip()
        if not name:
            raise bad_request("Step name is required.")
        step = WorkflowStep(
            tenant_id=self.tenant_id,
            workflow_id=workflow.id,
            name=name,
            order_number=STEP_TEMPORARY_ORDER_BASE,
            assigned_role=data.assigned_role.value,
        )
        self.db.add(step)
        await self.db.flush()
        ordered = list(steps)
        ordered.insert(data.order_number - 1, step)
        await self._assign_step_orders(ordered)
        await self.audit.log_event(
            event_type=AuditEventType.WORKFLOW_STEP_CREATED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="workflow_step",
            resource_id=step.id,
        )
        await self.db.commit()
        await self.db.refresh(step)
        return step

    async def update_step(
        self,
        workflow_id: UUID,
        step_id: UUID,
        data: WorkflowStepUpdate,
        *,
        user_id: UUID,
        email: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> WorkflowStep:
        await self._get_editable_workflow(workflow_id)
        step = await self.repository.get_step(workflow_id, step_id, for_update=True)
        if step is None:
            raise not_found("Workflow step")
        values = data.model_dump(exclude_unset=True)
        if "name" in values:
            name = str(values["name"]).strip()
            if not name:
                raise bad_request("Step name is required.")
            step.name = name
        if "assigned_role" in values and values["assigned_role"] is not None:
            step.assigned_role = values["assigned_role"].value
        if "order_number" in values and values["order_number"] != step.order_number:
            steps = await self.repository.get_steps(workflow_id, for_update=True)
            requested = values["order_number"]
            if not 1 <= requested <= len(steps):
                raise bad_request(
                    f"Step order_number must be between 1 and {len(steps)}."
                )
            ordered = [item for item in steps if item.id != step.id]
            ordered.insert(requested - 1, step)
            await self._assign_step_orders(ordered)
        await self.db.flush()
        await self.audit.log_event(
            event_type=AuditEventType.WORKFLOW_STEP_UPDATED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="workflow_step",
            resource_id=step.id,
        )
        await self.db.commit()
        await self.db.refresh(step)
        return step

    async def delete_step(
        self,
        workflow_id: UUID,
        step_id: UUID,
        *,
        user_id: UUID,
        email: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        await self._get_editable_workflow(workflow_id)
        step = await self.repository.get_step(workflow_id, step_id, for_update=True)
        if step is None:
            raise not_found("Workflow step")
        steps = await self.repository.get_steps(workflow_id, for_update=True)
        await self.db.delete(step)
        await self.db.flush()
        await self._assign_step_orders([item for item in steps if item.id != step.id])
        await self.audit.log_event(
            event_type=AuditEventType.WORKFLOW_STEP_DELETED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="workflow_step",
            resource_id=step.id,
        )
        await self.db.commit()

    async def start_execution(
        self,
        workflow_id: UUID,
        data: WorkflowExecutionCreate,
        *,
        user_id: UUID,
        email: str,
        actor_role: UserRole,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> WorkflowExecution:
        workflow = await self.repository.get_by_id(workflow_id)
        if workflow is None:
            raise not_found("Workflow")
        if workflow.status != WorkflowStatus.ACTIVE:
            raise bad_request("Only active workflows can be executed.")
        steps = await self.repository.get_steps(workflow.id)
        if not steps:
            raise bad_request("Workflow contains no steps.")
        self._validate_step_actor(steps[0], actor_role)
        now = utc_now()
        due_date = to_utc(data.due_date) if data.due_date is not None else None
        entity_type = data.entity_type.strip()
        if not entity_type:
            raise bad_request("Entity type is required.")
        execution = await self.execution_repository.create(
            WorkflowExecution(
                tenant_id=self.tenant_id,
                workflow_id=workflow.id,
                entity_type=entity_type,
                entity_id=data.entity_id,
                status=WorkflowExecutionStatus.IN_PROGRESS,
                current_step_id=steps[0].id,
                started_by=user_id,
                context=data.context,
                due_date=due_date,
                sla_status=SLAService.calculate_status(
                    created_at=now, due_date=due_date, now=now
                ),
            )
        )
        for index, step in enumerate(steps, start=1):
            is_first = index == 1
            await self.execution_repository.create_step_execution(
                WorkflowStepExecution(
                    tenant_id=self.tenant_id,
                    workflow_execution_id=execution.id,
                    workflow_step_id=step.id,
                    step_name=step.name,
                    order_number=index,
                    assigned_role=step.assigned_role,
                    status=(
                        WorkflowStepExecutionStatus.IN_PROGRESS
                        if is_first
                        else WorkflowStepExecutionStatus.PENDING
                    ),
                    started_at=now if is_first else None,
                )
            )
        await self._record_workflow_audit(
            execution_id=execution.id,
            step_name=steps[0].name,
            action=WorkflowAuditAction.WORKFLOW_STARTED,
            old_status=None,
            new_status=WorkflowExecutionStatus.IN_PROGRESS.value,
            user_id=user_id,
        )
        await self.audit.log_event(
            event_type=AuditEventType.WORKFLOW_EXECUTION_STARTED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="workflow_execution",
            resource_id=execution.id,
        )
        await self.db.commit()
        refreshed = await self.execution_repository.get_execution(execution.id)
        if refreshed is None:
            raise not_found("Workflow execution")
        return refreshed

    async def get_execution(self, execution_id: UUID) -> WorkflowExecution:
        execution = await self.execution_repository.get_execution(execution_id)
        if execution is None:
            raise not_found("Workflow execution")
        return execution

    async def advance_execution(
        self,
        execution_id: UUID,
        data: WorkflowAdvanceRequest,
        *,
        user_id: UUID,
        email: str,
        actor_role: UserRole,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> WorkflowExecution:
        execution = await self.execution_repository.get_execution(
            execution_id, for_update=True
        )
        if execution is None:
            raise not_found("Workflow execution")
        if execution.status != WorkflowExecutionStatus.IN_PROGRESS:
            raise bad_request("Only in-progress workflow executions can be advanced.")
        current_step = await self.execution_repository.get_in_progress_step(
            execution.id
        )
        if current_step is None:
            raise bad_request("Workflow execution has no active step.")
        if (
            actor_role.value != current_step.assigned_role
            and actor_role != UserRole.ADMINISTRATOR
        ):
            raise forbidden(
                "You are not authorized to complete the current workflow step."
            )
        now = utc_now()
        current_step.status = WorkflowStepExecutionStatus.COMPLETED
        current_step.completed_at = now
        current_step.notes = data.notes
        current_step.result = data.result
        await self._record_workflow_audit(
            execution_id=execution.id,
            step_name=current_step.step_name,
            action=WorkflowAuditAction.STEP_COMPLETED,
            old_status=WorkflowStepExecutionStatus.IN_PROGRESS.value,
            new_status=WorkflowStepExecutionStatus.COMPLETED.value,
            user_id=user_id,
            comments=data.notes,
        )
        step_executions = await self.execution_repository.get_step_executions(
            execution.id
        )
        next_step = next(
            (
                item
                for item in step_executions
                if item.order_number > current_step.order_number
                and item.status == WorkflowStepExecutionStatus.PENDING
            ),
            None,
        )
        await self.audit.log_event(
            event_type=AuditEventType.WORKFLOW_STEP_COMPLETED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="workflow_step_execution",
            resource_id=current_step.id,
        )
        if next_step is None:
            execution.status = WorkflowExecutionStatus.COMPLETED
            execution.current_step_id = None
            execution.completed_at = now
            await self._record_workflow_audit(
                execution_id=execution.id,
                step_name=current_step.step_name,
                action=WorkflowAuditAction.WORKFLOW_COMPLETED,
                old_status=WorkflowExecutionStatus.IN_PROGRESS.value,
                new_status=WorkflowExecutionStatus.COMPLETED.value,
                user_id=user_id,
                comments=data.notes,
            )
            await self._evaluate_workflow_sla(execution, now=now)
            await self.audit.log_event(
                event_type=AuditEventType.WORKFLOW_EXECUTION_COMPLETED,
                user_id=user_id,
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
                resource_type="workflow_execution",
                resource_id=execution.id,
            )
        else:
            next_step.status = WorkflowStepExecutionStatus.IN_PROGRESS
            next_step.started_at = now
            execution.current_step_id = next_step.workflow_step_id
            await self._record_workflow_audit(
                execution_id=execution.id,
                step_name=next_step.step_name,
                action=WorkflowAuditAction.STEP_STARTED,
                old_status=WorkflowStepExecutionStatus.PENDING.value,
                new_status=WorkflowStepExecutionStatus.IN_PROGRESS.value,
                user_id=user_id,
            )
        await self.db.commit()
        return await self.get_execution(execution.id)

    async def cancel_execution(
        self,
        execution_id: UUID,
        data: WorkflowExecutionCancelRequest,
        *,
        user_id: UUID,
        email: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> WorkflowExecution:
        execution = await self.execution_repository.get_execution(
            execution_id, for_update=True
        )
        if execution is None:
            raise not_found("Workflow execution")
        if execution.status != WorkflowExecutionStatus.IN_PROGRESS:
            raise bad_request("Only in-progress workflow executions can be cancelled.")
        execution.status = WorkflowExecutionStatus.CANCELLED
        execution.current_step_id = None
        execution.completed_at = utc_now()
        current_step = await self.execution_repository.get_in_progress_step(
            execution.id
        )
        if current_step is not None:
            current_step.status = WorkflowStepExecutionStatus.SKIPPED
            current_step.completed_at = execution.completed_at
            current_step.notes = data.notes
            await self._record_workflow_audit(
                execution_id=execution.id,
                step_name=current_step.step_name,
                action=WorkflowAuditAction.STEP_SKIPPED,
                old_status=WorkflowStepExecutionStatus.IN_PROGRESS.value,
                new_status=WorkflowStepExecutionStatus.SKIPPED.value,
                user_id=user_id,
                comments=data.notes,
            )
        await self._record_workflow_audit(
            execution_id=execution.id,
            step_name=current_step.step_name if current_step else None,
            action=WorkflowAuditAction.WORKFLOW_CANCELLED,
            old_status=WorkflowExecutionStatus.IN_PROGRESS.value,
            new_status=WorkflowExecutionStatus.CANCELLED.value,
            user_id=user_id,
            comments=data.notes,
        )
        await self.audit.log_event(
            event_type=AuditEventType.WORKFLOW_EXECUTION_CANCELLED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="workflow_execution",
            resource_id=execution.id,
        )
        await self.db.commit()
        return await self.get_execution(execution.id)

    async def fail_execution(
        self,
        execution_id: UUID,
        *,
        user_id: UUID,
        email: str,
        actor_role: UserRole,
        notes: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> WorkflowExecution:
        execution = await self.execution_repository.get_execution(
            execution_id, for_update=True
        )
        if execution is None:
            raise not_found("Workflow execution")
        if execution.status != WorkflowExecutionStatus.IN_PROGRESS:
            raise bad_request("Only an in-progress workflow execution can fail.")

        current_step = await self.execution_repository.get_in_progress_step(
            execution_id
        )
        if current_step is None:
            raise bad_request("The workflow execution does not have an active step.")
        self._validate_step_actor_from_snapshot(current_step, actor_role)

        now = utc_now()
        current_step.status = WorkflowStepExecutionStatus.FAILED
        current_step.notes = notes
        current_step.completed_at = now
        execution.status = WorkflowExecutionStatus.FAILED
        execution.completed_at = now
        await self.db.flush()

        await self._record_workflow_audit(
            execution_id=execution.id,
            step_name=current_step.step_name,
            action=WorkflowAuditAction.STEP_FAILED,
            old_status=WorkflowStepExecutionStatus.IN_PROGRESS.value,
            new_status=WorkflowStepExecutionStatus.FAILED.value,
            user_id=user_id,
            comments=notes,
        )
        await self.audit.log_event(
            event_type=AuditEventType.WORKFLOW_STEP_FAILED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="workflow_step_execution",
            resource_id=current_step.id,
        )
        await self._record_workflow_audit(
            execution_id=execution.id,
            step_name=current_step.step_name,
            action=WorkflowAuditAction.WORKFLOW_FAILED,
            old_status=WorkflowExecutionStatus.IN_PROGRESS.value,
            new_status=WorkflowExecutionStatus.FAILED.value,
            user_id=user_id,
            comments=notes,
        )
        await self.audit.log_event(
            event_type=AuditEventType.WORKFLOW_EXECUTION_FAILED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="workflow_execution",
            resource_id=execution.id,
        )
        await self.db.commit()
        return await self.get_execution(execution.id)

    async def retry_failed_execution(
        self,
        execution_id: UUID,
        *,
        user_id: UUID,
        email: str,
        actor_role: UserRole,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> WorkflowExecution:
        execution = await self.execution_repository.get_execution(
            execution_id, for_update=True
        )
        if execution is None:
            raise not_found("Workflow execution")
        if execution.status != WorkflowExecutionStatus.FAILED:
            raise bad_request("Only a failed workflow execution can be retried.")

        step_executions = await self.execution_repository.get_step_executions(
            execution.id
        )
        failed_step = next(
            (
                step
                for step in sorted(
                    step_executions, key=lambda item: item.order_number, reverse=True
                )
                if step.status == WorkflowStepExecutionStatus.FAILED
            ),
            None,
        )
        if failed_step is None:
            raise bad_request("The workflow execution does not have a failed step.")
        self._validate_step_actor_from_snapshot(failed_step, actor_role)

        failed_step.status = WorkflowStepExecutionStatus.IN_PROGRESS
        failed_step.started_at = utc_now()
        failed_step.completed_at = None
        failed_step.notes = None
        execution.status = WorkflowExecutionStatus.IN_PROGRESS
        execution.current_step_id = failed_step.workflow_step_id
        await self.db.flush()
        await self.audit.log_event(
            event_type=AuditEventType.WORKFLOW_STEP_RETRIED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="workflow_step_execution",
            resource_id=failed_step.id,
        )
        await self.db.commit()
        return await self.get_execution(execution.id)

    @staticmethod
    def _validate_step_actor_from_snapshot(
        step_execution: WorkflowStepExecution, actor_role: UserRole
    ) -> None:
        if actor_role == UserRole.ADMINISTRATOR:
            return
        if step_execution.assigned_role != actor_role.value:
            raise forbidden("You do not have permission to execute this workflow step.")

    async def get_audit_history(self, execution_id: UUID) -> list[WorkflowAuditLog]:
        execution = await self.execution_repository.get_execution(execution_id)
        if execution is None:
            raise not_found("Workflow execution")
        return await self.workflow_audit_repository.get_by_execution_id(execution_id)
