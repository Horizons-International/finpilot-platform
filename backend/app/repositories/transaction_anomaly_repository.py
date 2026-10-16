"""Tenant-scoped reads and writes for transaction anomaly analysis."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.transaction_anomaly import (
    TransactionAnomaly,
    TransactionAnomalyActivity,
)
from app.models.transaction_risk_analysis import TransactionRiskTransaction
from app.repositories.tenant_scoped_repository import TenantScopedRepository


class TransactionAnomalyRepository(TenantScopedRepository[TransactionAnomaly]):
    """Persistence boundary for one tenant's anomaly events and history."""

    def __init__(self, db: Session, tenant_id: UUID) -> None:
        super().__init__(db=db, model=TransactionAnomaly, tenant_id=tenant_id)

    def get_customer(self, customer_id: UUID) -> Customer | None:
        return (
            self.db.query(Customer)
            .filter(
                Customer.id == customer_id,
                Customer.tenant_id == self.tenant_id,
            )
            .first()
        )

    def activity_for_transaction_ids(
        self, transaction_ids: set[UUID]
    ) -> list[TransactionAnomalyActivity]:
        if not transaction_ids:
            return []
        statement = select(TransactionAnomalyActivity).where(
            TransactionAnomalyActivity.tenant_id == self.tenant_id,
            TransactionAnomalyActivity.transaction_id.in_(transaction_ids),
        )
        return list(self.db.scalars(statement).all())

    def risk_transactions_for_ids(
        self, transaction_ids: set[UUID]
    ) -> list[TransactionRiskTransaction]:
        if not transaction_ids:
            return []
        statement = select(TransactionRiskTransaction).where(
            TransactionRiskTransaction.tenant_id == self.tenant_id,
            TransactionRiskTransaction.transaction_id.in_(transaction_ids),
        )
        return list(self.db.scalars(statement).all())

    def list_activity_history(
        self,
        customer_id: UUID,
        *,
        cutoff: datetime,
        excluded_ids: set[UUID],
        limit: int,
    ) -> list[TransactionAnomalyActivity]:
        statement = select(TransactionAnomalyActivity).where(
            TransactionAnomalyActivity.tenant_id == self.tenant_id,
            TransactionAnomalyActivity.customer_id == customer_id,
            TransactionAnomalyActivity.occurred_at >= cutoff,
        )
        if excluded_ids:
            statement = statement.where(
                ~TransactionAnomalyActivity.transaction_id.in_(excluded_ids)
            )
        statement = statement.order_by(
            TransactionAnomalyActivity.occurred_at.desc()
        ).limit(limit)
        return list(self.db.scalars(statement).all())

    def list_risk_transaction_history(
        self,
        customer_id: UUID,
        *,
        cutoff: datetime,
        excluded_ids: set[UUID],
        limit: int,
    ) -> list[TransactionRiskTransaction]:
        statement = select(TransactionRiskTransaction).where(
            TransactionRiskTransaction.tenant_id == self.tenant_id,
            TransactionRiskTransaction.customer_id == customer_id,
            TransactionRiskTransaction.occurred_at >= cutoff,
        )
        if excluded_ids:
            statement = statement.where(
                ~TransactionRiskTransaction.transaction_id.in_(excluded_ids)
            )
        statement = statement.order_by(
            TransactionRiskTransaction.occurred_at.desc()
        ).limit(limit)
        return list(self.db.scalars(statement).all())

    def existing_activity_ids(self, transaction_ids: set[UUID]) -> set[UUID]:
        if not transaction_ids:
            return set()
        statement = select(TransactionAnomalyActivity.transaction_id).where(
            TransactionAnomalyActivity.tenant_id == self.tenant_id,
            TransactionAnomalyActivity.transaction_id.in_(transaction_ids),
        )
        return set(self.db.scalars(statement).all())

    def create_activities(self, activities: list[TransactionAnomalyActivity]) -> None:
        for activity in activities:
            if activity.tenant_id != self.tenant_id:
                raise ValueError("Activity tenant does not match repository tenant.")
        if activities:
            self.db.add_all(activities)

    def create_anomalies(self, anomalies: list[TransactionAnomaly]) -> None:
        for anomaly in anomalies:
            if anomaly.tenant_id != self.tenant_id:
                raise ValueError("Anomaly tenant does not match repository tenant.")
        if anomalies:
            self.db.add_all(anomalies)

    def list_anomalies(
        self,
        *,
        customer_id: UUID | None = None,
        limit: int = 100,
    ) -> list[TransactionAnomaly]:
        query = self.query()
        if customer_id is not None:
            query = query.filter(TransactionAnomaly.customer_id == customer_id)
        return query.order_by(TransactionAnomaly.created_at.desc()).limit(limit).all()

    def get_anomaly(self, anomaly_id: UUID) -> TransactionAnomaly | None:
        return self.get_by_id(anomaly_id)
