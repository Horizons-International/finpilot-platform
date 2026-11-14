"""Native-async tenant-scoped persistence for transaction anomaly analysis."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.transaction_anomaly import (
    TransactionAnomaly,
    TransactionAnomalyActivity,
)
from app.models.transaction_risk_analysis import TransactionRiskTransaction


class AsyncTransactionAnomalyRepository:
    """Persistence boundary for one tenant's anomaly events and activity."""

    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        active_tenant = db.info.get("tenant_id")
        if active_tenant is not None and active_tenant != tenant_id:
            raise ValueError("Anomaly repository tenant does not match the session.")
        db.info["tenant_id"] = tenant_id
        self.db = db
        self.tenant_id = tenant_id

    async def get_customer(
        self, customer_id: UUID, *, for_update: bool = False
    ) -> Customer | None:
        statement = select(Customer).where(
            Customer.id == customer_id,
            Customer.tenant_id == self.tenant_id,
        )
        if for_update:
            # Serialize analysis for one customer. This makes a concurrent
            # duplicate submission re-check transaction ownership after the
            # first request commits instead of racing through the pre-check.
            statement = statement.with_for_update()
        return await self.db.scalar(statement)

    async def activity_for_transaction_ids(
        self, transaction_ids: set[UUID]
    ) -> list[TransactionAnomalyActivity]:
        if not transaction_ids:
            return []
        result = await self.db.scalars(
            select(TransactionAnomalyActivity).where(
                TransactionAnomalyActivity.tenant_id == self.tenant_id,
                TransactionAnomalyActivity.transaction_id.in_(transaction_ids),
            )
        )
        return list(result.all())

    async def risk_transactions_for_ids(
        self, transaction_ids: set[UUID]
    ) -> list[TransactionRiskTransaction]:
        if not transaction_ids:
            return []
        result = await self.db.scalars(
            select(TransactionRiskTransaction).where(
                TransactionRiskTransaction.tenant_id == self.tenant_id,
                TransactionRiskTransaction.transaction_id.in_(transaction_ids),
            )
        )
        return list(result.all())

    async def list_activity_history(
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
        result = await self.db.scalars(
            statement.order_by(TransactionAnomalyActivity.occurred_at.desc()).limit(
                limit
            )
        )
        return list(result.all())

    async def list_risk_transaction_history(
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
        result = await self.db.scalars(
            statement.order_by(TransactionRiskTransaction.occurred_at.desc()).limit(
                limit
            )
        )
        return list(result.all())

    async def existing_activity_ids(self, transaction_ids: set[UUID]) -> set[UUID]:
        if not transaction_ids:
            return set()
        result = await self.db.scalars(
            select(TransactionAnomalyActivity.transaction_id).where(
                TransactionAnomalyActivity.tenant_id == self.tenant_id,
                TransactionAnomalyActivity.transaction_id.in_(transaction_ids),
            )
        )
        return set(result.all())

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

    async def list_anomalies(
        self,
        *,
        customer_id: UUID | None = None,
        limit: int = 100,
    ) -> list[TransactionAnomaly]:
        statement = select(TransactionAnomaly).where(
            TransactionAnomaly.tenant_id == self.tenant_id
        )
        if customer_id is not None:
            statement = statement.where(TransactionAnomaly.customer_id == customer_id)
        result = await self.db.scalars(
            statement.order_by(TransactionAnomaly.created_at.desc()).limit(limit)
        )
        return list(result.all())

    async def get_anomaly(self, anomaly_id: UUID) -> TransactionAnomaly | None:
        return await self.db.scalar(
            select(TransactionAnomaly).where(
                TransactionAnomaly.id == anomaly_id,
                TransactionAnomaly.tenant_id == self.tenant_id,
            )
        )
