from uuid import UUID

from sqlalchemy.orm import Session

from app.models.risk_scoring_rule import RiskScoringRule
from app.repositories.risk_scoring_rule_repository import (
    RiskScoringRuleRepository,
)
from app.schemas.risk_scoring import (
    RiskScoringRuleCreate,
    RiskScoringRuleUpdate,
)
from app.services.audit_service import AuditService
from app.utils.enums import AuditEventType
from app.utils.errors import bad_request, not_found


class RiskScoringRuleService:
    def __init__(self, db: Session) -> None:
        self.repository = RiskScoringRuleRepository(db)
        self.audit_service = AuditService(db)
        self.db = db

    def create(
        self,
        *,
        data: RiskScoringRuleCreate,
        user_id: UUID,
        email: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> RiskScoringRule:
        rule = RiskScoringRule(
            factor_key=data.factor_key,
            operator=data.operator,
            expected_value=data.expected_value,
            score_points=data.score_points,
            description=data.description,
            priority=data.priority,
            is_active=data.is_active,
        )

        rule = self.repository.create(rule)

        self.audit_service.log_event(
            user_id=user_id,
            email=email,
            event_type=AuditEventType.RISK_SCORING_RULE_CREATED,
            resource_type="risk_scoring_rule",
            resource_id=rule.id,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        self.db.commit()
        self.db.refresh(rule)

        return rule

    def list_all(
        self,
    ) -> list[RiskScoringRule]:
        return self.repository.get_all()

    def get_by_id(
        self,
        rule_id: UUID,
    ) -> RiskScoringRule:
        rule = self.repository.get_by_id(rule_id)

        if rule is None:
            raise not_found("Risk scoring rule")

        return rule

    def update(
        self,
        *,
        rule_id: UUID,
        data: RiskScoringRuleUpdate,
        user_id: UUID,
        email: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> RiskScoringRule:
        rule = self.get_by_id(rule_id)

        update_data = data.model_dump(exclude_unset=True)

        if not update_data:
            raise bad_request("At least one field must be provided for update.")

        for field, value in update_data.items():
            setattr(rule, field, value)

        rule = self.repository.update(rule)

        self.audit_service.log_event(
            user_id=user_id,
            email=email,
            event_type=AuditEventType.RISK_SCORING_RULE_UPDATED,
            resource_type="risk_scoring_rule",
            resource_id=rule.id,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        self.db.commit()
        self.db.refresh(rule)

        return rule

    def update_status(
        self,
        *,
        rule_id: UUID,
        is_active: bool,
        user_id: UUID,
        email: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> RiskScoringRule:
        rule = self.get_by_id(rule_id)

        if rule.is_active == is_active:
            raise bad_request("Risk scoring rule is already in this status.")

        rule.is_active = is_active

        rule = self.repository.update(rule)

        self.audit_service.log_event(
            user_id=user_id,
            email=email,
            event_type=AuditEventType.RISK_SCORING_RULE_STATUS_CHANGED,
            resource_type="risk_scoring_rule",
            resource_id=rule.id,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        self.db.commit()
        self.db.refresh(rule)

        return rule

    def delete(
        self,
        *,
        rule_id: UUID,
        user_id: UUID,
        email: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> None:
        rule = self.get_by_id(rule_id)

        self.repository.delete(rule)

        self.audit_service.log_event(
            user_id=user_id,
            email=email,
            event_type=AuditEventType.RISK_SCORING_RULE_DELETED,
            resource_type="risk_scoring_rule",
            resource_id=rule.id,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        self.db.commit()
