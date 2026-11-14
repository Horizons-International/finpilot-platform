"""Native-async CRUD for tenant-scoped workflow task-assignment rules."""

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task_assignment_rule import TaskAssignmentRule
from app.models.user import User
from app.models.workflow import Workflow, WorkflowStep
from app.schemas.task_assignment_rule import (
    TaskAssignmentRuleCreate,
    TaskAssignmentRuleUpdate,
)
from app.services.async_audit_service import AsyncAuditService
from app.utils.enums import AuditEventType
from app.utils.errors import bad_request, not_found


class AsyncTaskAssignmentRuleService:
    """Manage assignment rules; automatic assignment is handled by AsyncTaskService."""

    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        active_tenant = db.info.get("tenant_id")
        if active_tenant is not None and active_tenant != tenant_id:
            raise ValueError("Task assignment tenant does not match the session.")
        db.info["tenant_id"] = tenant_id
        self.db = db
        self.tenant_id = tenant_id
        self.audit = AsyncAuditService(db)

    @staticmethod
    def _normalize_conditions(conditions: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(conditions)
        role = normalized.get("role")
        if role is not None:
            normalized["role"] = role.value if hasattr(role, "value") else str(role)
        department = normalized.get("department")
        if department is not None:
            department = str(department).strip()
            normalized["department"] = department or None
        country = normalized.get("country")
        if country is not None:
            country = str(country).strip().upper()
            normalized["country"] = country or None
        return {key: value for key, value in normalized.items() if value is not None}

    async def _validate_relations(
        self,
        *,
        created_by: UUID | None,
        workflow_id: UUID | None,
        workflow_step_id: UUID | None,
        conditions: dict[str, Any],
    ) -> None:
        if created_by is not None:
            owner = await self.db.scalar(
                select(User.id).where(
                    User.id == created_by,
                    User.tenant_id == self.tenant_id,
                )
            )
            if owner is None:
                raise bad_request("Rule creator does not belong to the current tenant.")
        if workflow_id is not None:
            workflow = await self.db.scalar(
                select(Workflow.id).where(
                    Workflow.id == workflow_id,
                    Workflow.tenant_id == self.tenant_id,
                )
            )
            if workflow is None:
                raise not_found("Workflow")
        if workflow_step_id is not None:
            if workflow_id is None:
                raise bad_request(
                    "workflow_id is required when workflow_step_id is provided."
                )
            step = await self.db.scalar(
                select(WorkflowStep).where(
                    WorkflowStep.id == workflow_step_id,
                    WorkflowStep.tenant_id == self.tenant_id,
                )
            )
            if step is None:
                raise not_found("Workflow step")
            if step.workflow_id != workflow_id:
                raise bad_request(
                    "Workflow step does not belong to the specified workflow."
                )
            requested_role = conditions.get("role")
            if requested_role is not None and requested_role != step.assigned_role:
                raise bad_request(
                    "Assignment rule role must match the workflow step assigned role."
                )

    async def _by_name(self, name: str) -> TaskAssignmentRule | None:
        return await self.db.scalar(
            select(TaskAssignmentRule).where(
                TaskAssignmentRule.tenant_id == self.tenant_id,
                TaskAssignmentRule.name == name,
            )
        )

    async def _by_id_for_update(self, rule_id: UUID) -> TaskAssignmentRule | None:
        return await self.db.scalar(
            select(TaskAssignmentRule)
            .where(
                TaskAssignmentRule.id == rule_id,
                TaskAssignmentRule.tenant_id == self.tenant_id,
            )
            .with_for_update()
        )

    async def create_rule(
        self,
        data: TaskAssignmentRuleCreate,
        *,
        user_id: UUID,
        email: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> TaskAssignmentRule:
        name = data.name.strip()
        if not name:
            raise bad_request("Assignment rule name is required.")
        if await self._by_name(name) is not None:
            raise bad_request("An assignment rule with this name already exists.")
        conditions = self._normalize_conditions(
            data.conditions.model_dump(exclude_none=True)
        )
        await self._validate_relations(
            created_by=user_id,
            workflow_id=data.workflow_id,
            workflow_step_id=data.workflow_step_id,
            conditions=conditions,
        )
        rule = TaskAssignmentRule(
            tenant_id=self.tenant_id,
            name=name,
            description=data.description,
            workflow_id=data.workflow_id,
            workflow_step_id=data.workflow_step_id,
            conditions=conditions,
            strategy=data.strategy,
            priority=data.priority,
            is_active=False,
            created_by=user_id,
        )
        self.db.add(rule)
        await self.db.flush()
        await self.audit.log_event(
            event_type=AuditEventType.TASK_ASSIGNMENT_RULE_CREATED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="task_assignment_rule",
            resource_id=rule.id,
        )
        await self.db.commit()
        await self.db.refresh(rule)
        return rule

    async def update_rule(
        self,
        rule_id: UUID,
        data: TaskAssignmentRuleUpdate,
        *,
        user_id: UUID,
        email: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> TaskAssignmentRule:
        rule = await self._by_id_for_update(rule_id)
        if rule is None:
            raise not_found("Task assignment rule")
        if rule.is_active:
            raise bad_request(
                "Active assignment rules cannot be edited. "
                "Deactivate the rule before editing it."
            )
        update_data = data.model_dump(exclude_unset=True)
        if not update_data:
            raise bad_request("No assignment rule fields were provided.")
        if "name" in update_data:
            name = str(update_data["name"]).strip()
            if not name:
                raise bad_request("Assignment rule name is required.")
            existing = await self._by_name(name)
            if existing is not None and existing.id != rule.id:
                raise bad_request("An assignment rule with this name already exists.")
            rule.name = name
        if "description" in update_data:
            rule.description = update_data["description"]
        workflow_id = update_data.get("workflow_id", rule.workflow_id)
        workflow_step_id = update_data.get("workflow_step_id", rule.workflow_step_id)
        conditions_data = update_data.get("conditions")
        conditions = (
            self._normalize_conditions(conditions_data)
            if conditions_data is not None
            else dict(rule.conditions or {})
        )
        await self._validate_relations(
            created_by=rule.created_by,
            workflow_id=workflow_id,
            workflow_step_id=workflow_step_id,
            conditions=conditions,
        )
        rule.workflow_id = workflow_id
        rule.workflow_step_id = workflow_step_id
        rule.conditions = conditions
        if "strategy" in update_data and update_data["strategy"] is not None:
            rule.strategy = update_data["strategy"]
        if "priority" in update_data and update_data["priority"] is not None:
            rule.priority = update_data["priority"]
        await self.db.flush()
        await self.audit.log_event(
            event_type=AuditEventType.TASK_ASSIGNMENT_RULE_UPDATED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="task_assignment_rule",
            resource_id=rule.id,
        )
        await self.db.commit()
        await self.db.refresh(rule)
        return rule

    async def set_active(
        self,
        rule_id: UUID,
        is_active: bool,
        *,
        user_id: UUID,
        email: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> TaskAssignmentRule:
        rule = await self._by_id_for_update(rule_id)
        if rule is None:
            raise not_found("Task assignment rule")
        if rule.is_active == is_active:
            raise bad_request("Assignment rule already has this status.")
        rule.is_active = is_active
        await self.db.flush()
        await self.audit.log_event(
            event_type=AuditEventType.TASK_ASSIGNMENT_RULE_STATUS_CHANGED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="task_assignment_rule",
            resource_id=rule.id,
        )
        await self.db.commit()
        await self.db.refresh(rule)
        return rule

    async def list_rules(
        self,
        *,
        is_active: bool | None = None,
        workflow_id: UUID | None = None,
        workflow_step_id: UUID | None = None,
    ) -> list[TaskAssignmentRule]:
        statement = select(TaskAssignmentRule).where(
            TaskAssignmentRule.tenant_id == self.tenant_id
        )
        if is_active is not None:
            statement = statement.where(TaskAssignmentRule.is_active == is_active)
        if workflow_id is not None:
            statement = statement.where(TaskAssignmentRule.workflow_id == workflow_id)
        if workflow_step_id is not None:
            statement = statement.where(
                TaskAssignmentRule.workflow_step_id == workflow_step_id
            )
        result = await self.db.scalars(
            statement.order_by(
                TaskAssignmentRule.priority.asc(),
                TaskAssignmentRule.created_at.asc(),
            )
        )
        return list(result.all())
