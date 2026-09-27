from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.transaction_monitoring_result import (
    TransactionMonitoringResult,
)
from app.repositories.aml_rule_repository import AMLRuleRepository
from app.repositories.transaction_monitoring_result_repository import (
    TransactionMonitoringResultRepository,
)
from app.schemas.transaction_monitoring import (
    TransactionMonitoringRequest,
)
from app.services.aml_rule_engine import AMLRuleEngine
from app.services.audit_service import AuditService
from app.utils.enums import (
    AMLRuleType,
    AuditEventType,
    TransactionMonitoringOutcome,
)


class TransactionMonitoringService:
    def __init__(self, db: Session) -> None:
        self.db = db

        self.aml_rule_repository = AMLRuleRepository(db)

        self.result_repository = TransactionMonitoringResultRepository(db)

        self.engine = AMLRuleEngine()

        self.audit_service = AuditService(db)

    def monitor_transaction(
        self,
        *,
        payload: TransactionMonitoringRequest,
        user_id: UUID,
        email: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> list[TransactionMonitoringResult]:
        rules = self.aml_rule_repository.get_active_by_type(
            AMLRuleType.TRANSACTION,
        )

        evaluation_data: dict[str, Any] = {
            "customer_id": payload.customer_id,
            "transaction_id": payload.transaction_id,
            "amount": payload.amount,
            "currency": payload.currency,
            "country": payload.country,
            "transaction_type": payload.transaction_type,
            "transaction_date": payload.transaction_date,
        }

        evaluation = self.engine.evaluate(
            rule_type=AMLRuleType.TRANSACTION,
            rules=rules,
            data=evaluation_data,
        )

        persisted_results: list[TransactionMonitoringResult] = []

        for evaluated_rule in evaluation.evaluations:
            outcome = (
                TransactionMonitoringOutcome.MATCHED
                if evaluated_rule.matched
                else TransactionMonitoringOutcome.NOT_MATCHED
            )

            monitoring_result = TransactionMonitoringResult(
                transaction_id=payload.transaction_id,
                customer_id=payload.customer_id,
                rule_id=evaluated_rule.rule_id,
                result=outcome,
            )

            persisted_result = self.result_repository.create(
                monitoring_result,
            )

            persisted_results.append(persisted_result)

            self.audit_service.log_event(
                user_id=user_id,
                email=email,
                event_type=AuditEventType.AML_RULE_EVALUATED,
                resource_type="aml_rule",
                resource_id=evaluated_rule.rule_id,
                ip_address=ip_address,
                user_agent=user_agent,
            )

        self.db.commit()

        return persisted_results
