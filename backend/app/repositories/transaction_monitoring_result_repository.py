from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.transaction_monitoring_result import (
    TransactionMonitoringResult,
)


class TransactionMonitoringResultRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        monitoring_result: TransactionMonitoringResult,
    ) -> TransactionMonitoringResult:
        self.db.add(monitoring_result)
        self.db.flush()
        self.db.refresh(monitoring_result)

        return monitoring_result

    def get_by_transaction_id(
        self,
        transaction_id: UUID,
    ) -> list[TransactionMonitoringResult]:
        statement = (
            select(TransactionMonitoringResult)
            .where(TransactionMonitoringResult.transaction_id == transaction_id)
            .order_by(TransactionMonitoringResult.created_at.desc())
        )

        return list(self.db.scalars(statement).all())
