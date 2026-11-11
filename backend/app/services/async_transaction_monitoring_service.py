"""Async AML transaction monitoring orchestration."""

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.transaction_monitoring_result import TransactionMonitoringResult
from app.repositories.async_aml_rule_repository import AsyncAMLRuleRepository
from app.repositories.async_transaction_monitoring_result_repository import (
    AsyncTransactionMonitoringResultRepository,
)
from app.schemas.transaction_monitoring import TransactionMonitoringRequest
from app.services.aml_rule_engine import AMLRuleEngine
from app.services.async_audit_service import AsyncAuditService
from app.services.subscription_service import record_subscription_usage
from app.utils.enums import AMLRuleType, AuditEventType, TransactionMonitoringOutcome
from app.utils.errors import not_found


class AsyncTransactionMonitoringService:
    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.db.info["tenant_id"] = tenant_id
        self.rule_repository = AsyncAMLRuleRepository(db, tenant_id)
        self.result_repository = AsyncTransactionMonitoringResultRepository(
            db, tenant_id
        )
        self.engine = AMLRuleEngine()
        self.audit_service = AsyncAuditService(db)

    async def monitor_transaction(
        self,
        *,
        payload: TransactionMonitoringRequest,
        user_id: UUID,
        email: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> list[TransactionMonitoringResult]:
        customer_id = await self.db.scalar(
            select(Customer.id).where(
                Customer.id == payload.customer_id,
                Customer.tenant_id == self.tenant_id,
            )
        )
        if customer_id is None:
            raise not_found("Customer")

        # Keep subscription metering identical to the existing service while
        # moving the caller and all monitoring persistence to AsyncSession.
        await self.db.run_sync(
            lambda sync_db: record_subscription_usage(
                sync_db, self.tenant_id, "transactions"
            )
        )
        rules = await self.rule_repository.get_active_by_type(AMLRuleType.TRANSACTION)
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
            result = await self.result_repository.create(
                TransactionMonitoringResult(
                    tenant_id=self.tenant_id,
                    transaction_id=payload.transaction_id,
                    customer_id=payload.customer_id,
                    rule_id=evaluated_rule.rule_id,
                    country=payload.country,
                    result=outcome,
                )
            )
            persisted_results.append(result)
            await self.audit_service.log_event(
                event_type=AuditEventType.AML_RULE_EVALUATED,
                user_id=user_id,
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
                resource_type="aml_rule",
                resource_id=evaluated_rule.rule_id,
            )
        await self.db.commit()
        return persisted_results
