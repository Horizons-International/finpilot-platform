from typing import Any
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.task import Task, TaskStatusHistory
from app.models.task_assignment_rule import TaskAssignmentRule
from app.models.user import User
from app.models.workflow import (
    WorkflowExecution,
    WorkflowStep,
    WorkflowStepExecution,
)
from app.repositories.task_assignment_rule_repository import (
    TaskAssignmentRuleRepository,
)
from app.services.audit_service import AuditService
from app.utils.date_time import utc_now
from app.utils.enums import (
    AuditEventType,
    TaskAssignmentStrategy,
    TaskStatus,
    UserRole,
    UserStatus,
)
from app.utils.errors import bad_request, not_found

ACTIVE_TASK_STATUSES = {
    TaskStatus.NEW,
    TaskStatus.ASSIGNED,
    TaskStatus.IN_PROGRESS,
}


class TaskAssignmentService:
    def __init__(
        self,
        db: Session,
    ) -> None:
        self.db = db
        self.repository = TaskAssignmentRuleRepository(db)
        self.audit_service = AuditService(db)

    # ------------------------------------------------------------------
    # Rule management
    # ------------------------------------------------------------------

    def _validate_rule_scope(
        self,
        *,
        workflow_id: UUID | None,
        workflow_step_id: UUID | None,
        conditions: dict[str, Any],
    ) -> None:
        if workflow_step_id is not None and workflow_id is None:
            raise bad_request(
                "workflow_id is required when workflow_step_id is provided.",
            )

        if workflow_step_id is None:
            return

        step = (
            self.db.query(WorkflowStep)
            .filter(
                WorkflowStep.id == workflow_step_id,
            )
            .first()
        )

        if step is None:
            raise not_found("Workflow step")

        if step.workflow_id != workflow_id:
            raise bad_request(
                "Workflow step does not belong to the specified workflow.",
            )

        requested_role = conditions.get("role")

        if requested_role is None:
            return

        if requested_role != step.assigned_role:
            raise bad_request(
                "Assignment rule role must match the workflow step assigned role.",
            )

    def _normalize_conditions(
        self,
        conditions: dict[str, Any],
    ) -> dict[str, Any]:
        normalized = dict(conditions)

        role = normalized.get("role")

        if role is not None:
            normalized["role"] = role.value if isinstance(role, UserRole) else str(role)

        department = normalized.get("department")

        if department is not None:
            department = str(department).strip()

            normalized["department"] = department if department else None

        country = normalized.get("country")

        if country is not None:
            country = str(country).strip().upper()

            normalized["country"] = country if country else None

        return {key: value for key, value in normalized.items() if value is not None}

    def create_rule(
        self,
        data,
        *,
        user_id: UUID,
        email: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> TaskAssignmentRule:
        name = data.name.strip()

        if not name:
            raise bad_request(
                "Assignment rule name is required.",
            )

        if self.repository.get_by_name(name) is not None:
            raise bad_request(
                "An assignment rule with this name already exists.",
            )

        conditions = self._normalize_conditions(
            data.conditions.model_dump(
                exclude_none=True,
            ),
        )

        self._validate_rule_scope(
            workflow_id=data.workflow_id,
            workflow_step_id=data.workflow_step_id,
            conditions=conditions,
        )

        rule = TaskAssignmentRule(
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

        self.repository.create(rule)

        self.audit_service.log_event(
            event_type=AuditEventType.TASK_ASSIGNMENT_RULE_CREATED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="task_assignment_rule",
            resource_id=rule.id,
        )

        self.db.commit()
        self.db.refresh(rule)

        return rule

    def update_rule(
        self,
        rule_id: UUID,
        data,
        *,
        user_id: UUID,
        email: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> TaskAssignmentRule:
        rule = self.repository.get_by_id_for_update(
            rule_id,
        )

        if rule is None:
            raise not_found("Task assignment rule")

        if rule.is_active:
            raise bad_request(
                "Active assignment rules cannot be edited. "
                "Deactivate the rule before editing it.",
            )

        update_data = data.model_dump(
            exclude_unset=True,
        )

        if not update_data:
            raise bad_request(
                "No assignment rule fields were provided.",
            )

        if "name" in update_data:
            name = str(update_data["name"]).strip()

            if not name:
                raise bad_request(
                    "Assignment rule name is required.",
                )

            existing = self.repository.get_by_name(name)

            if existing is not None and existing.id != rule.id:
                raise bad_request(
                    "An assignment rule with this name already exists.",
                )

            rule.name = name

        if "description" in update_data:
            rule.description = update_data["description"]

        workflow_id = update_data.get(
            "workflow_id",
            rule.workflow_id,
        )

        workflow_step_id = update_data.get(
            "workflow_step_id",
            rule.workflow_step_id,
        )

        conditions = update_data.get(
            "conditions",
        )

        if conditions is None:
            normalized_conditions = dict(
                rule.conditions,
            )
        else:
            normalized_conditions = self._normalize_conditions(
                conditions,
            )

        self._validate_rule_scope(
            workflow_id=workflow_id,
            workflow_step_id=workflow_step_id,
            conditions=normalized_conditions,
        )

        rule.workflow_id = workflow_id
        rule.workflow_step_id = workflow_step_id
        rule.conditions = normalized_conditions

        if "strategy" in update_data:
            rule.strategy = update_data["strategy"]

        if "priority" in update_data:
            rule.priority = update_data["priority"]

        self.repository.update(rule)

        self.audit_service.log_event(
            event_type=AuditEventType.TASK_ASSIGNMENT_RULE_UPDATED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="task_assignment_rule",
            resource_id=rule.id,
        )

        self.db.commit()
        self.db.refresh(rule)

        return rule

    def set_active(
        self,
        rule_id: UUID,
        is_active: bool,
        *,
        user_id: UUID,
        email: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> TaskAssignmentRule:
        rule = self.repository.get_by_id_for_update(
            rule_id,
        )

        if rule is None:
            raise not_found("Task assignment rule")

        if rule.is_active == is_active:
            raise bad_request(
                "Assignment rule already has this status.",
            )

        rule.is_active = is_active

        self.repository.update(rule)

        self.audit_service.log_event(
            event_type=(AuditEventType.TASK_ASSIGNMENT_RULE_STATUS_CHANGED),
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="task_assignment_rule",
            resource_id=rule.id,
        )

        self.db.commit()
        self.db.refresh(rule)

        return rule

    def list_rules(
        self,
        *,
        is_active: bool | None = None,
        workflow_id: UUID | None = None,
        workflow_step_id: UUID | None = None,
    ) -> list[TaskAssignmentRule]:
        return self.repository.list_rules(
            is_active=is_active,
            workflow_id=workflow_id,
            workflow_step_id=workflow_step_id,
        )

    # ------------------------------------------------------------------
    # Automatic task assignment
    # ------------------------------------------------------------------

    def apply_to_task(
        self,
        task: Task,
        *,
        user_id: UUID,
        email: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> User | None:
        if task.assigned_to is not None:
            return None

        if task.workflow_execution_id is None:
            return None

        if task.workflow_step_execution_id is None:
            return None

        execution = (
            self.db.query(WorkflowExecution)
            .filter(
                WorkflowExecution.id == task.workflow_execution_id,
            )
            .first()
        )

        if execution is None:
            raise not_found("Workflow execution")

        step_execution = (
            self.db.query(WorkflowStepExecution)
            .filter(
                WorkflowStepExecution.id == task.workflow_step_execution_id,
            )
            .first()
        )

        if step_execution is None:
            raise not_found("Workflow step execution")

        if step_execution.workflow_execution_id != execution.id:
            raise bad_request(
                "Workflow step execution does not belong to the workflow execution.",
            )

        country = self._resolve_task_country(
            task,
            execution,
        )

        rules = self.repository.list_rules(
            is_active=True,
        )

        ranked_rules = self._rank_rules(
            rules,
            execution=execution,
            step_execution=step_execution,
        )

        for rule in ranked_rules:
            if not self._rule_matches(
                rule,
                country=country,
                step_execution=step_execution,
            ):
                continue

            candidates = self._get_candidates(
                rule=rule,
                step_execution=step_execution,
            )

            if not candidates:
                continue

            selected_user = self._select_user(
                candidates,
                strategy=rule.strategy,
            )

            if selected_user is None:
                continue

            old_status = task.status

            task.assigned_to = selected_user.id
            task.assignment_rule_id = rule.id

            if task.status == TaskStatus.NEW:
                task.status = TaskStatus.ASSIGNED

                history = TaskStatusHistory(
                    task_id=task.id,
                    changed_by=user_id,
                    from_status=old_status,
                    to_status=TaskStatus.ASSIGNED,
                    changed_at=utc_now(),
                )

                self.db.add(history)

            self.db.flush()

            self.audit_service.log_event(
                event_type=AuditEventType.TASK_ASSIGNMENT_RULE_APPLIED,
                user_id=user_id,
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
                resource_type="task_assignment_rule",
                resource_id=rule.id,
            )

            self.audit_service.log_event(
                event_type=AuditEventType.TASK_AUTO_ASSIGNED,
                user_id=user_id,
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
                resource_type="task",
                resource_id=task.id,
            )

            return selected_user

        return None

    def _rank_rules(
        self,
        rules: list[TaskAssignmentRule],
        *,
        execution: WorkflowExecution,
        step_execution: WorkflowStepExecution,
    ) -> list[TaskAssignmentRule]:
        def specificity(rule: TaskAssignmentRule) -> tuple[int, int]:
            scope_specificity = (
                2
                if rule.workflow_step_id == step_execution.workflow_step_id
                else (1 if rule.workflow_id == execution.workflow_id else 0)
            )

            condition_specificity = len(
                rule.conditions or {},
            )

            return (
                scope_specificity,
                condition_specificity,
            )

        return sorted(
            rules,
            key=lambda rule: (
                rule.priority,
                -specificity(rule)[0],
                -specificity(rule)[1],
                rule.created_at,
                str(rule.id),
            ),
        )

    def _rule_matches(
        self,
        rule: TaskAssignmentRule,
        *,
        country: str | None,
        step_execution: WorkflowStepExecution,
    ) -> bool:
        if rule.workflow_step_id is not None:
            if rule.workflow_step_id != step_execution.workflow_step_id:
                return False

        conditions = rule.conditions or {}

        requested_country = conditions.get(
            "country",
        )

        if requested_country is not None:
            if country is None:
                return False

            if (
                country.upper()
                != str(
                    requested_country,
                ).upper()
            ):
                return False

        requested_role = conditions.get(
            "role",
        )

        if requested_role is not None:
            if requested_role != step_execution.assigned_role:
                return False

        return True

    def _get_candidates(
        self,
        *,
        rule: TaskAssignmentRule,
        step_execution: WorkflowStepExecution,
    ) -> list[User]:
        conditions = rule.conditions or {}

        requested_role = conditions.get("role")

        if requested_role is None:
            requested_role = step_execution.assigned_role

        requested_department = conditions.get(
            "department",
        )

        query = self.db.query(User).filter(
            User.status == UserStatus.ACTIVE,
            User.is_deleted.is_(False),
            User.role == requested_role,
        )

        if requested_department is not None:
            query = query.filter(
                User.department == requested_department,
            )

        candidate_users = (
            query.order_by(
                User.id.asc(),
            )
            .with_for_update()
            .all()
        )

        return candidate_users

    def _select_user(
        self,
        candidates: list[User],
        *,
        strategy: TaskAssignmentStrategy,
    ) -> User | None:
        if not candidates:
            return None

        if strategy != TaskAssignmentStrategy.LEAST_LOADED:
            raise bad_request(
                "Unsupported task assignment strategy.",
            )

        best_user: User | None = None
        best_workload: int | None = None

        for user in candidates:
            workload = (
                self.db.query(
                    func.count(Task.id),
                )
                .filter(
                    Task.assigned_to == user.id,
                    Task.status.in_(
                        ACTIVE_TASK_STATUSES,
                    ),
                )
                .scalar()
                or 0
            )

            if (
                best_workload is None
                or workload < best_workload
                or (
                    workload == best_workload
                    and (best_user is None or str(user.id) < str(best_user.id))
                )
            ):
                best_user = user
                best_workload = workload

        return best_user

    def _resolve_task_country(
        self,
        task: Task,
        execution: WorkflowExecution,
    ) -> str | None:
        context = execution.context or {}

        country = context.get("country")

        if country:
            return str(country).strip().upper()

        country = context.get(
            "country_of_residence",
        )

        if country:
            return str(country).strip().upper()

        if execution.entity_type == "customer":
            customer = (
                self.db.query(Customer)
                .filter(
                    Customer.id == execution.entity_id,
                )
                .first()
            )

            if customer is not None:
                if customer.country_of_residence:
                    return customer.country_of_residence.strip().upper()

        return None
