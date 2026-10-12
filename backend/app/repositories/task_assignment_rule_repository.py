from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.task_assignment_rule import TaskAssignmentRule
from app.models.user import User
from app.models.workflow import Workflow, WorkflowStep
from app.repositories.tenant_scoped_repository import TenantScopedRepository


class TaskAssignmentRuleRepository(TenantScopedRepository[TaskAssignmentRule]):
    """Tenant-scoped assignment rules with tenant-checked relationships."""

    def __init__(
        self,
        db: Session,
        tenant_id: UUID | None = None,
    ) -> None:
        resolved_tenant_id = tenant_id or db.info.get("tenant_id")
        if not isinstance(resolved_tenant_id, UUID):
            raise ValueError("A tenant context is required for task assignment rules.")
        session_tenant_id = db.info.get("tenant_id")
        if session_tenant_id is not None and session_tenant_id != resolved_tenant_id:
            raise ValueError(
                "The SQLAlchemy session is already bound to another tenant."
            )
        # Also scope relationship/lazy loads covered by tenant_filter.py.
        db.info["tenant_id"] = resolved_tenant_id
        super().__init__(db=db, model=TaskAssignmentRule, tenant_id=resolved_tenant_id)

    def _validate_relations(self, rule: TaskAssignmentRule) -> None:
        if rule.created_by is not None:
            user_id = self.db.scalar(
                select(User.id).where(
                    User.id == rule.created_by,
                    User.tenant_id == self.tenant_id,
                )
            )
            if user_id is None:
                raise ValueError("Rule creator does not belong to the current tenant.")

        workflow_id = rule.workflow_id
        if workflow_id is not None:
            owned_workflow_id = self.db.scalar(
                select(Workflow.id).where(
                    Workflow.id == workflow_id,
                    Workflow.tenant_id == self.tenant_id,
                )
            )
            if owned_workflow_id is None:
                raise ValueError("Rule workflow does not belong to the current tenant.")

        step_id = rule.workflow_step_id
        if step_id is not None:
            step = self.db.scalar(
                select(WorkflowStep).where(
                    WorkflowStep.id == step_id,
                    WorkflowStep.tenant_id == self.tenant_id,
                )
            )
            if step is None:
                raise ValueError(
                    "Rule workflow step does not belong to the current tenant."
                )
            if workflow_id is not None and step.workflow_id != workflow_id:
                raise ValueError("Rule workflow and workflow step do not match.")

    def _assert_owned(self, rule: TaskAssignmentRule) -> None:
        if rule.tenant_id != self.tenant_id:
            raise ValueError("Task assignment rule belongs to another tenant.")
        exists = self.db.scalar(
            select(TaskAssignmentRule.id).where(
                TaskAssignmentRule.id == rule.id,
                TaskAssignmentRule.tenant_id == self.tenant_id,
            )
        )
        if exists is None:
            raise ValueError(
                "Task assignment rule does not belong to the current tenant."
            )

    def create(self, rule: TaskAssignmentRule) -> TaskAssignmentRule:
        if rule.tenant_id is not None and rule.tenant_id != self.tenant_id:
            raise ValueError("Cannot create a task assignment rule for another tenant.")
        self._validate_relations(rule)
        return super().create(rule)

    def get_by_name(self, name: str) -> TaskAssignmentRule | None:
        return self.query().filter(TaskAssignmentRule.name == name).first()

    def get_by_id_for_update(self, rule_id: UUID) -> TaskAssignmentRule | None:
        return (
            self.query()
            .filter(TaskAssignmentRule.id == rule_id)
            .with_for_update()
            .first()
        )

    def list_rules(
        self,
        *,
        is_active: bool | None = None,
        workflow_id: UUID | None = None,
        workflow_step_id: UUID | None = None,
    ) -> list[TaskAssignmentRule]:
        query = self.query()
        if is_active is not None:
            query = query.filter(TaskAssignmentRule.is_active == is_active)
        if workflow_id is not None:
            query = query.filter(TaskAssignmentRule.workflow_id == workflow_id)
        if workflow_step_id is not None:
            query = query.filter(
                TaskAssignmentRule.workflow_step_id == workflow_step_id
            )
        return query.order_by(
            TaskAssignmentRule.priority.asc(),
            TaskAssignmentRule.created_at.asc(),
        ).all()

    def update(self, rule: TaskAssignmentRule) -> TaskAssignmentRule:
        self._assert_owned(rule)
        self._validate_relations(rule)
        self.db.flush()
        self.db.refresh(rule)
        return rule

    def delete(self, rule: TaskAssignmentRule) -> None:
        self._assert_owned(rule)
        self.db.delete(rule)
        self.db.flush()
