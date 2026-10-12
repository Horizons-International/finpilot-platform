from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.aml_rule import AMLRule
from app.models.customer import Customer
from app.models.transaction_monitoring_result import TransactionMonitoringResult
from app.repositories.tenant_scoped_repository import (
    TenantScopedRepository,
    resolve_tenant_id,
)


class TransactionMonitoringResultRepository:
    def __init__(
        self,
        db: Session,
        tenant_id: UUID | None = None,
    ) -> None:
        resolved = resolve_tenant_id(db, tenant_id)
        assert resolved is not None
        self.db = db
        self.tenant_id = resolved
        self._scoped = TenantScopedRepository(
            db,
            TransactionMonitoringResult,
            resolved,
        )

    def create(
        self,
        monitoring_result: TransactionMonitoringResult,
    ) -> TransactionMonitoringResult:
        if (
            monitoring_result.tenant_id is not None
            and monitoring_result.tenant_id != self.tenant_id
        ):
            raise ValueError("Cannot create a monitoring result for another tenant.")

        customer_exists = self.db.scalar(
            select(Customer.id).where(
                Customer.id == monitoring_result.customer_id,
                Customer.tenant_id == self.tenant_id,
            )
        )
        if customer_exists is None:
            raise ValueError("Monitoring result customer is outside this tenant.")

        rule_exists = self.db.scalar(
            select(AMLRule.id).where(
                AMLRule.id == monitoring_result.rule_id,
                AMLRule.tenant_id == self.tenant_id,
            )
        )
        if rule_exists is None:
            raise ValueError("Monitoring rule is outside this tenant.")

        return self._scoped.create(monitoring_result)

    def get_by_transaction_id(
        self,
        transaction_id: UUID,
    ) -> list[TransactionMonitoringResult]:
        statement = (
            select(TransactionMonitoringResult)
            .where(
                TransactionMonitoringResult.tenant_id == self.tenant_id,
                TransactionMonitoringResult.transaction_id == transaction_id,
            )
            .order_by(TransactionMonitoringResult.created_at.desc())
        )
        return list(self.db.scalars(statement).all())
