from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.customer_risk_profile import CustomerRiskProfile
from app.repositories.customer_repository import CustomerRepository
from app.repositories.customer_risk_profile_repository import (
    CustomerRiskProfileRepository,
)
from app.repositories.risk_score_threshold_repository import (
    RiskScoreThresholdRepository,
)
from app.repositories.risk_scoring_rule_repository import (
    RiskScoringRuleRepository,
)
from app.services.audit_service import AuditService
from app.services.risk_scoring_engine import RiskScoringEngine
from app.utils.enums import AuditEventType
from app.utils.errors import not_found


class RiskScoringService:
    def __init__(self, db: Session) -> None:
        self.db = db

        self.customer_repository = CustomerRepository(db)

        self.profile_repository = CustomerRiskProfileRepository(db)

        self.rule_repository = RiskScoringRuleRepository(db)

        self.threshold_repository = RiskScoreThresholdRepository(db)

        self.audit_service = AuditService(db)

        self.engine = RiskScoringEngine()

    def calculate_and_store(
        self,
        *,
        customer_id: UUID,
        factors: dict[str, Any],
        risk_category: str,
        assessment_source: str,
        user_id: UUID,
        email: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> CustomerRiskProfile:
        customer = self.customer_repository.get_by_id(customer_id)

        if customer is None:
            raise not_found("Customer")

        rules = self.rule_repository.get_active_rules()

        thresholds = self.threshold_repository.get_active_thresholds()

        result = self.engine.calculate(
            factors=factors,
            rules=rules,
            thresholds=thresholds,
        )

        now = datetime.now(timezone.utc)

        profile = self.profile_repository.get_by_customer_id(
            customer_id,
        )

        calculation_details = {
            "factors": factors,
            "applied_rules": [
                {
                    "rule_id": rule.rule_id,
                    "factor_key": rule.factor_key,
                    "score_points": rule.score_points,
                }
                for rule in result.applied_rules
            ],
        }

        if profile is None:
            profile = CustomerRiskProfile(
                customer_id=customer_id,
                risk_level=result.risk_level,
                risk_score=result.score,
                risk_category=risk_category,
                assessed_at=now,
                assessment_source=assessment_source,
                calculation_details=calculation_details,
            )

            self.db.add(profile)
            self.db.flush()

            event_type = AuditEventType.CUSTOMER_RISK_PROFILE_CREATED

        else:
            profile.risk_level = result.risk_level
            profile.risk_score = result.score
            profile.risk_category = risk_category
            profile.assessed_at = now
            profile.assessment_source = assessment_source
            profile.calculation_details = calculation_details

            self.db.flush()

            event_type = AuditEventType.CUSTOMER_RISK_PROFILE_UPDATED

        self.audit_service.log_event(
            event_type=event_type,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="customer_risk_profile",
            resource_id=profile.id,
        )

        self.db.commit()
        self.db.refresh(profile)

        self.audit_service.log_event(
            event_type=AuditEventType.CUSTOMER_RISK_SCORE_CALCULATED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="customer_risk_profile",
            resource_id=profile.id,
        )

        return profile
