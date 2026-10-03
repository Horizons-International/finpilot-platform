from collections.abc import Sequence
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.workflow import (
    Workflow,
    WorkflowExecution,
    WorkflowStep,
    WorkflowStepExecution,
)
from app.repositories.workflow_execution_repository import (
    WorkflowExecutionRepository,
)
from app.repositories.workflow_repository import WorkflowRepository
from app.schemas.workflow import (
    WorkflowAdvanceRequest,
    WorkflowCreate,
    WorkflowExecutionCancelRequest,
    WorkflowExecutionCreate,
    WorkflowStepCreate,
    WorkflowStepUpdate,
    WorkflowUpdate,
)
from app.services.audit_service import AuditService
from app.services.sla_service import SLAService
from app.utils.date_time import to_utc, utc_now
from app.utils.enums import (
    AuditEventType,
    UserRole,
    WorkflowExecutionStatus,
    WorkflowStatus,
    WorkflowStepExecutionStatus,
)
from app.utils.errors import bad_request, forbidden, not_found

WORKFLOW_STATUS_TRANSITIONS: dict[
    WorkflowStatus,
    set[WorkflowStatus],
] = {
    WorkflowStatus.DRAFT: {
        WorkflowStatus.ACTIVE,
        WorkflowStatus.INACTIVE,
    },
    WorkflowStatus.ACTIVE: {
        WorkflowStatus.INACTIVE,
    },
    WorkflowStatus.INACTIVE: {
        WorkflowStatus.ACTIVE,
    },
}

STEP_TEMPORARY_ORDER_BASE = 1_000_000


class WorkflowService:
    def __init__(
        self,
        db: Session,
    ) -> None:
        self.db = db
        self.sla_service = SLAService(db)
        self.repository = WorkflowRepository(db)
        self.execution_repository = WorkflowExecutionRepository(db)
        self.audit_service = AuditService(db)

    # ------------------------------------------------------------------
    # Workflow definitions
    # ------------------------------------------------------------------

    def create_workflow(
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

        if self.repository.get_by_name(name) is not None:
            raise bad_request(
                "A workflow with this name already exists.",
            )

        workflow = Workflow(
            name=name,
            description=data.description,
            status=WorkflowStatus.DRAFT,
        )

        self.repository.create(workflow)

        self.audit_service.log_event(
            event_type=AuditEventType.WORKFLOW_CREATED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="workflow",
            resource_id=workflow.id,
        )

        self.db.commit()
        self.db.refresh(workflow)

        return workflow

    def get_workflow(
        self,
        workflow_id: UUID,
    ) -> Workflow:
        workflow = self.repository.get_by_id(workflow_id)

        if workflow is None:
            raise not_found("Workflow")

        # Force the relationship to be loaded while the session is active.
        workflow.steps

        return workflow

    def list_workflows(
        self,
        *,
        status: WorkflowStatus | None = None,
    ) -> list[Workflow]:
        workflows = self.repository.get_all(
            status=status,
        )

        for workflow in workflows:
            workflow.steps

        return workflows

    def update_workflow(
        self,
        workflow_id: UUID,
        data: WorkflowUpdate,
        *,
        user_id: UUID,
        email: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> Workflow:
        workflow = self._get_editable_workflow(
            workflow_id,
        )

        update_data = data.model_dump(
            exclude_unset=True,
        )

        if not update_data:
            return workflow

        if "name" in update_data:
            name = str(update_data["name"]).strip()

            if not name:
                raise bad_request(
                    "Workflow name is required.",
                )

            existing = self.repository.get_by_name(name)

            if existing is not None and existing.id != workflow.id:
                raise bad_request(
                    "A workflow with this name already exists.",
                )

            workflow.name = name

        if "description" in update_data:
            workflow.description = update_data["description"]

        self.repository.update(workflow)

        self.audit_service.log_event(
            event_type=AuditEventType.WORKFLOW_UPDATED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="workflow",
            resource_id=workflow.id,
        )

        self.db.commit()
        self.db.refresh(workflow)

        return workflow

    def update_workflow_status(
        self,
        workflow_id: UUID,
        new_status: WorkflowStatus,
        *,
        user_id: UUID,
        email: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> Workflow:
        workflow = self.repository.get_by_id(workflow_id)

        if workflow is None:
            raise not_found("Workflow")

        if workflow.status == new_status:
            raise bad_request(
                "Workflow is already in this status.",
            )

        allowed_statuses = WORKFLOW_STATUS_TRANSITIONS.get(
            workflow.status,
            set(),
        )

        if new_status not in allowed_statuses:
            raise bad_request(
                f"Invalid workflow status transition: "
                f"{workflow.status.value} -> {new_status.value}.",
            )

        if new_status == WorkflowStatus.ACTIVE:
            steps = self.repository.get_steps(
                workflow.id,
            )

            if not steps:
                raise bad_request(
                    "A workflow must contain at least "
                    "one step before it can be activated.",
                )

        old_status = workflow.status

        workflow.status = new_status

        self.repository.update(workflow)

        self.audit_service.log_event(
            event_type=AuditEventType.WORKFLOW_STATUS_CHANGED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="workflow",
            resource_id=workflow.id,
        )

        self.db.commit()
        self.db.refresh(workflow)

        _ = old_status

        return workflow

    # ------------------------------------------------------------------
    # Workflow steps
    # ------------------------------------------------------------------

    def add_step(
        self,
        workflow_id: UUID,
        data: WorkflowStepCreate,
        *,
        user_id: UUID,
        email: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> WorkflowStep:
        workflow = self._get_editable_workflow(
            workflow_id,
        )

        steps = self.repository.get_steps(
            workflow.id,
            for_update=True,
        )

        next_order = len(steps) + 1

        if data.order_number > next_order:
            raise bad_request(
                f"Step order_number cannot be greater than {next_order}.",
            )

        step = WorkflowStep(
            workflow_id=workflow.id,
            name=data.name.strip(),
            order_number=STEP_TEMPORARY_ORDER_BASE,
            assigned_role=data.assigned_role.value,
        )

        if not step.name:
            raise bad_request("Step name is required.")

        self.db.add(step)
        self.db.flush()

        ordered_steps = list(steps)

        insert_index = data.order_number - 1

        ordered_steps.insert(
            insert_index,
            step,
        )

        self._assign_step_orders(
            ordered_steps,
        )

        self.db.refresh(step)

        self.audit_service.log_event(
            event_type=AuditEventType.WORKFLOW_STEP_CREATED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="workflow_step",
            resource_id=step.id,
        )

        self.db.commit()
        self.db.refresh(step)

        return step

    def update_step(
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
        self._get_editable_workflow(
            workflow_id,
        )

        step = self.repository.get_step(
            workflow_id,
            step_id,
            for_update=True,
        )

        if step is None:
            raise not_found("Workflow step")

        update_data = data.model_dump(
            exclude_unset=True,
        )

        if "name" in update_data:
            name = str(update_data["name"]).strip()

            if not name:
                raise bad_request(
                    "Step name is required.",
                )

            step.name = name

        if "assigned_role" in update_data:
            assigned_role = update_data["assigned_role"]

            if assigned_role is not None:
                step.assigned_role = assigned_role.value

        if "order_number" in update_data:
            requested_order = update_data["order_number"]

            if requested_order != step.order_number:
                steps = self.repository.get_steps(
                    workflow_id,
                    for_update=True,
                )

                if not 1 <= requested_order <= len(steps):
                    raise bad_request(
                        f"Step order_number must be between 1 and {len(steps)}.",
                    )

                ordered_steps = [item for item in steps if item.id != step.id]

                ordered_steps.insert(
                    requested_order - 1,
                    step,
                )

                self._assign_step_orders(
                    ordered_steps,
                )

        self.db.flush()
        self.db.refresh(step)

        self.audit_service.log_event(
            event_type=AuditEventType.WORKFLOW_STEP_UPDATED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="workflow_step",
            resource_id=step.id,
        )

        self.db.commit()
        self.db.refresh(step)

        return step

    def delete_step(
        self,
        workflow_id: UUID,
        step_id: UUID,
        *,
        user_id: UUID,
        email: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        self._get_editable_workflow(
            workflow_id,
        )

        step = self.repository.get_step(
            workflow_id,
            step_id,
            for_update=True,
        )

        if step is None:
            raise not_found("Workflow step")

        steps = self.repository.get_steps(
            workflow_id,
            for_update=True,
        )

        self.db.delete(step)
        self.db.flush()

        remaining_steps = [item for item in steps if item.id != step.id]

        self._assign_step_orders(
            remaining_steps,
        )

        self.audit_service.log_event(
            event_type=AuditEventType.WORKFLOW_STEP_DELETED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="workflow_step",
            resource_id=step.id,
        )

        self.db.commit()

    # ------------------------------------------------------------------
    # Workflow execution
    # ------------------------------------------------------------------

    def start_execution(
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
        workflow = self.repository.get_by_id(
            workflow_id,
        )

        if workflow is None:
            raise not_found("Workflow")

        if workflow.status != WorkflowStatus.ACTIVE:
            raise bad_request(
                "Only active workflows can be executed.",
            )

        steps = self.repository.get_steps(
            workflow.id,
        )

        if not steps:
            raise bad_request(
                "Workflow contains no steps.",
            )

        self._validate_step_actor(
            steps[0],
            actor_role,
        )

        now = utc_now()

        due_date = to_utc(data.due_date) if data.due_date is not None else None

        initial_sla_status = SLAService.calculate_status(
            created_at=now,
            due_date=due_date,
            now=now,
        )

        execution = WorkflowExecution(
            workflow_id=workflow.id,
            entity_type=data.entity_type.strip(),
            entity_id=data.entity_id,
            status=WorkflowExecutionStatus.IN_PROGRESS,
            current_step_id=steps[0].id,
            started_by=user_id,
            context=data.context,
            due_date=due_date,
            sla_status=initial_sla_status,
        )

        if not execution.entity_type:
            raise bad_request(
                "Entity type is required.",
            )

        self.execution_repository.create(
            execution,
        )

        for index, step in enumerate(
            steps,
            start=1,
        ):
            step_execution = WorkflowStepExecution(
                workflow_execution_id=execution.id,
                workflow_step_id=step.id,
                step_name=step.name,
                order_number=index,
                assigned_role=step.assigned_role,
                status=WorkflowStepExecutionStatus.PENDING,
            )

            if index == 1:
                step_execution.status = WorkflowStepExecutionStatus.IN_PROGRESS
                step_execution.started_at = now

            self.execution_repository.create_step_execution(
                step_execution,
            )

        self.audit_service.log_event(
            event_type=AuditEventType.WORKFLOW_EXECUTION_STARTED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="workflow_execution",
            resource_id=execution.id,
        )

        self.db.commit()

        refreshed_execution = self.execution_repository.get_by_id(
            execution.id,
        )

        if refreshed_execution is None:
            raise not_found("Workflow execution")

        refreshed_execution.step_executions

        return refreshed_execution

    def get_execution(
        self,
        execution_id: UUID,
    ) -> WorkflowExecution:
        execution = self.execution_repository.get_by_id(
            execution_id,
        )

        if execution is None:
            raise not_found("Workflow execution")

        execution.step_executions

        return execution

    def advance_execution(
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
        execution = self.execution_repository.get_by_id_for_update(
            execution_id,
        )

        if execution is None:
            raise not_found("Workflow execution")

        if execution.status != WorkflowExecutionStatus.IN_PROGRESS:
            raise bad_request(
                "Only in-progress workflow executions can be advanced.",
            )

        current_step = self.execution_repository.get_in_progress_step(
            execution.id,
        )

        if current_step is None:
            raise bad_request(
                "Workflow execution has no active step.",
            )

        if (
            actor_role.value != current_step.assigned_role
            and actor_role != UserRole.ADMINISTRATOR
        ):
            raise forbidden(
                "You are not authorized to complete the current workflow step.",
            )

        now = utc_now()

        current_step.status = WorkflowStepExecutionStatus.COMPLETED
        current_step.completed_at = now
        current_step.notes = data.notes
        current_step.result = data.result

        step_executions = self.execution_repository.get_step_executions(
            execution.id,
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

        self.audit_service.log_event(
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

            self.sla_service.evaluate_workflow(
                execution,
                now=now,
            )

            self.audit_service.log_event(
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

        self.db.commit()

        refreshed_execution = self.execution_repository.get_by_id(
            execution.id,
        )

        if refreshed_execution is None:
            raise not_found("Workflow execution")

        refreshed_execution.step_executions

        return refreshed_execution

    def cancel_execution(
        self,
        execution_id: UUID,
        data: WorkflowExecutionCancelRequest,
        *,
        user_id: UUID,
        email: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> WorkflowExecution:
        execution = self.execution_repository.get_by_id_for_update(
            execution_id,
        )

        if execution is None:
            raise not_found("Workflow execution")

        if execution.status != WorkflowExecutionStatus.IN_PROGRESS:
            raise bad_request(
                "Only in-progress workflow executions can be cancelled.",
            )

        execution.status = WorkflowExecutionStatus.CANCELLED
        execution.current_step_id = None
        execution.completed_at = utc_now()

        current_step = self.execution_repository.get_in_progress_step(
            execution.id,
        )

        if current_step is not None:
            current_step.status = WorkflowStepExecutionStatus.SKIPPED
            current_step.completed_at = execution.completed_at
            current_step.notes = data.notes

        self.audit_service.log_event(
            event_type=AuditEventType.WORKFLOW_EXECUTION_CANCELLED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="workflow_execution",
            resource_id=execution.id,
        )

        self.db.commit()

        refreshed_execution = self.execution_repository.get_by_id(
            execution.id,
        )

        if refreshed_execution is None:
            raise not_found("Workflow execution")

        refreshed_execution.step_executions

        return refreshed_execution

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_editable_workflow(
        self,
        workflow_id: UUID,
    ) -> Workflow:
        workflow = self.repository.get_by_id(
            workflow_id,
        )

        if workflow is None:
            raise not_found("Workflow")

        if workflow.status == WorkflowStatus.ACTIVE:
            raise bad_request(
                "Active workflows cannot be modified. "
                "Deactivate the workflow before modifying it.",
            )

        if self.execution_repository.has_execution_for_workflow(
            workflow.id,
        ):
            raise bad_request(
                "This workflow already has executions and cannot be modified.",
            )

        return workflow

    def _assign_step_orders(
        self,
        steps: Sequence[WorkflowStep],
    ) -> None:
        if not steps:
            return

        temporary_base = STEP_TEMPORARY_ORDER_BASE + len(steps)

        for index, step in enumerate(
            steps,
            start=1,
        ):
            step.order_number = temporary_base + index

        self.db.flush()

        for index, step in enumerate(
            steps,
            start=1,
        ):
            step.order_number = index

        self.db.flush()

    def _validate_step_actor(
        self,
        step,
        actor_role: UserRole,
    ) -> None:
        if actor_role == UserRole.ADMINISTRATOR:
            return

        if step.assigned_role != actor_role.value:
            raise forbidden("You do not have permission to execute this workflow step.")

    def fail_execution(
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
        execution = self.execution_repository.get_by_id_for_update(
            execution_id,
        )

        if execution is None:
            raise not_found("Workflow execution")

        if execution.status != WorkflowExecutionStatus.IN_PROGRESS:
            raise bad_request("Only an in-progress workflow execution can fail.")

        current_step = self.execution_repository.get_in_progress_step(
            execution_id,
        )

        if current_step is None:
            raise bad_request("The workflow execution does not have an active step.")

        self._validate_step_actor(
            current_step.workflow_step,
            actor_role,
        )

        current_step.status = WorkflowStepExecutionStatus.FAILED
        current_step.notes = notes
        current_step.completed_at = utc_now()

        execution.status = WorkflowExecutionStatus.FAILED

        self.db.flush()

        self.audit_service.log_event(
            event_type=AuditEventType.WORKFLOW_STEP_FAILED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="workflow_step_execution",
            resource_id=current_step.id,
        )

        self.audit_service.log_event(
            event_type=AuditEventType.WORKFLOW_EXECUTION_FAILED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="workflow_execution",
            resource_id=execution.id,
        )

        self.db.commit()
        self.db.refresh(execution)

        return execution

    def retry_failed_execution(
        self,
        execution_id: UUID,
        *,
        user_id: UUID,
        email: str,
        actor_role: UserRole,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> WorkflowExecution:
        execution = self.execution_repository.get_by_id_for_update(
            execution_id,
        )

        if execution is None:
            raise not_found("Workflow execution")

        if execution.status != WorkflowExecutionStatus.FAILED:
            raise bad_request("Only a failed workflow execution can be retried.")

        failed_step = (
            self.db.query(WorkflowStepExecution)
            .filter(
                WorkflowStepExecution.workflow_execution_id == execution.id,
                WorkflowStepExecution.status == WorkflowStepExecutionStatus.FAILED,
            )
            .order_by(
                WorkflowStepExecution.order_number.desc(),
            )
            .first()
        )

        if failed_step is None:
            raise bad_request("The workflow execution does not have a failed step.")

        self._validate_step_actor(
            failed_step.workflow_step,
            actor_role,
        )

        failed_step.status = WorkflowStepExecutionStatus.IN_PROGRESS
        failed_step.started_at = utc_now()
        failed_step.completed_at = None
        failed_step.notes = None

        execution.status = WorkflowExecutionStatus.IN_PROGRESS
        execution.current_step_id = failed_step.workflow_step_id

        self.db.flush()

        self.audit_service.log_event(
            event_type=AuditEventType.WORKFLOW_STEP_RETRIED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="workflow_step_execution",
            resource_id=failed_step.id,
        )

        self.db.commit()
        self.db.refresh(execution)

        return execution
