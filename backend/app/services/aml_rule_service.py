from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.aml_rule import AMLRule
from app.repositories.aml_rule_repository import AMLRuleRepository
from app.schemas.aml_rule import AMLRuleCreate
from app.services.aml_rule_engine import (
    AMLRuleEngine,
    AMLRuleEvaluationResult,
)
from app.services.audit_service import AuditService
from app.utils.enums import AMLRuleStatus, AMLRuleType, AuditEventType
from app.utils.errors import bad_request, not_found


class AMLRuleService:
    def __init__(
        self,
        db: Session,
    ) -> None:
        self.db = db
        self.repository = AMLRuleRepository(db)
        self.engine = AMLRuleEngine()
        self.audit_service = AuditService(db)

    def create(
        self,
        *,
        data: AMLRuleCreate,
        user_id: UUID,
        email: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> AMLRule:
        try:
            self.engine.validate_condition(
                data.condition,
            )
        except ValueError as exc:
            raise bad_request(str(exc))

        rule = AMLRule(
            name=data.name,
            description=data.description,
            rule_type=data.rule_type,
            condition=data.condition,
            severity=data.severity,
            status=data.status,
        )

        rule = self.repository.create(rule)

        self.audit_service.log_event(
            user_id=user_id,
            email=email,
            event_type=AuditEventType.AML_RULE_CREATED,
            resource_type="aml_rule",
            resource_id=rule.id,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        self.db.commit()
        self.db.refresh(rule)

        return rule

    def list_all(
        self,
    ) -> list[AMLRule]:
        return self.repository.get_all()

    def get_by_id(
        self,
        rule_id: UUID,
    ) -> AMLRule:
        rule = self.repository.get_by_id(
            rule_id,
        )

        if rule is None:
            raise not_found("AML rule")

        return rule

    def update_status(
        self,
        *,
        rule_id: UUID,
        new_status: AMLRuleStatus,
        user_id: UUID,
        email: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> AMLRule:
        rule = self.get_by_id(rule_id)

        if rule.status == new_status:
            raise bad_request("AML rule is already in the requested status.")

        rule.status = new_status

        rule = self.repository.update(rule)

        self.audit_service.log_event(
            user_id=user_id,
            email=email,
            event_type=AuditEventType.AML_RULE_STATUS_CHANGED,
            resource_type="aml_rule",
            resource_id=rule.id,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        self.db.commit()
        self.db.refresh(rule)

        return rule

    def evaluate(
        self,
        *,
        rule_type: AMLRuleType,
        data: dict[str, Any],
        user_id: UUID | None = None,
        email: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AMLRuleEvaluationResult:
        rules = self.repository.get_active_by_type(
            rule_type,
        )

        result = self.engine.evaluate(
            rule_type=rule_type,
            rules=rules,
            data=data,
        )

        if user_id is not None and email is not None:
            for evaluation in result.evaluations:
                self.audit_service.log_event(
                    user_id=user_id,
                    email=email,
                    event_type=AuditEventType.AML_RULE_EVALUATED,
                    resource_type="aml_rule",
                    resource_id=evaluation.rule_id,
                    ip_address=ip_address,
                    user_agent=user_agent,
                )

        self.db.commit()

        return result
