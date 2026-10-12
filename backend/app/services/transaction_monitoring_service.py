from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.transaction_monitoring_result import TransactionMonitoringResult
from app.repositories.aml_rule_repository import AMLRuleRepository
from app.repositories.transaction_monitoring_result_repository import (
    TransactionMonitoringResultRepository,
)
from app.schemas.transaction_monitoring import TransactionMonitoringRequest
from app.services.aml_rule_engine import AMLRuleEngine
from app.services.audit_service import AuditService
from app.services.tenant_context import resolve_tenant_context
from app.utils.enums import AMLRuleType, AuditEventType, TransactionMonitoringOutcome
from app.utils.errors import not_found


class TransactionMonitoringService:
    def __init__(self, db: Session, tenant_id: UUID | None = None) -> None:
        self.db = db
        self.tenant_id = resolve_tenant_context(
            db, tenant_id, resource_name="transaction monitoring"
        )
        self.aml_rule_repository = AMLRuleRepository(db, tenant_id=self.tenant_id)
        self.result_repository = TransactionMonitoringResultRepository(
            db, tenant_id=self.tenant_id
        )
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
        customer = self.db.scalar(
            select(Customer).where(
                Customer.id == payload.customer_id,
                Customer.tenant_id == self.tenant_id,
            )
        )
        if customer is None:
            raise not_found("Customer")

        rules = self.aml_rule_repository.get_active_by_type(AMLRuleType.TRANSACTION)
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
                tenant_id=self.tenant_id,
                transaction_id=payload.transaction_id,
                customer_id=payload.customer_id,
                rule_id=evaluated_rule.rule_id,
                country=payload.country,
                result=outcome,
            )
            persisted_result = self.result_repository.create(monitoring_result)
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
