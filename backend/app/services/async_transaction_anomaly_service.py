"""Native-async transaction anomaly detection and history persistence."""

from datetime import timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transaction_anomaly import (
    TransactionAnomaly,
    TransactionAnomalyActivity,
)
from app.repositories.async_transaction_anomaly_repository import (
    AsyncTransactionAnomalyRepository,
)
from app.schemas.transaction_anomaly import TransactionAnomalyAnalysisRequest
from app.services.transaction_anomaly_service import (
    _HISTORY_DAYS,
    _MAX_STORED_HISTORY,
    _input_activity,
    _risk_activity,
    _risk_level,
    _stored_activity,
)
from app.services.transaction_anomaly_service import (
    TransactionAnomalyService as _LegacyAlgorithm,
)
from app.utils.date_time import utc_now
from app.utils.errors import not_found


class AsyncTransactionAnomalyService:
    """Detect transaction deviations using async, tenant-scoped persistence.

    The existing deterministic detector is reused as a pure-Python algorithm;
    no synchronous ORM operation is called by this service.
    """

    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        active_tenant = db.info.get("tenant_id")
        if active_tenant is not None and active_tenant != tenant_id:
            raise ValueError("The session is already bound to another tenant.")
        db.info["tenant_id"] = tenant_id
        self.db = db
        self.tenant_id = tenant_id
        self.repository = AsyncTransactionAnomalyRepository(db, tenant_id)

    async def analyze(
        self, payload: TransactionAnomalyAnalysisRequest
    ) -> tuple[list[TransactionAnomaly], str]:
        customer = await self.repository.get_customer(
            payload.customer_id, for_update=True
        )
        if customer is None:
            raise not_found("Customer")

        current = [_input_activity(item) for item in payload.transactions]
        current_ids = {item.transaction_id for item in current}
        historical_input = [
            _input_activity(item) for item in payload.historical_transactions
        ]
        historical_ids = {item.transaction_id for item in historical_input}

        if historical_ids:
            historical_activity_owners = (
                await self.repository.activity_for_transaction_ids(historical_ids)
            )
            historical_risk_owners = await self.repository.risk_transactions_for_ids(
                historical_ids
            )
            historical_customer_ids = [
                row.customer_id for row in historical_activity_owners
            ] + [row.customer_id for row in historical_risk_owners]
            if any(
                customer_id != payload.customer_id
                for customer_id in historical_customer_ids
            ):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "A historical transaction ID is already associated with "
                        "another customer."
                    ),
                )

        # Tenant-wide ID ownership checks must run before staging any records.
        already_observed = await self.repository.activity_for_transaction_ids(
            current_ids
        )
        if already_observed:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="One or more transaction IDs have already been analyzed.",
            )

        risk_rows_for_current_ids = await self.repository.risk_transactions_for_ids(
            current_ids
        )
        if any(
            row.customer_id != payload.customer_id for row in risk_rows_for_current_ids
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A transaction ID is already associated with another customer.",
            )

        cutoff = utc_now() - timedelta(days=_HISTORY_DAYS)
        stored_rows = await self.repository.list_activity_history(
            payload.customer_id,
            cutoff=cutoff,
            excluded_ids=current_ids,
            limit=_MAX_STORED_HISTORY,
        )
        risk_history_rows = await self.repository.list_risk_transaction_history(
            payload.customer_id,
            cutoff=cutoff,
            excluded_ids=current_ids,
            limit=_MAX_STORED_HISTORY,
        )

        history_by_id: dict[UUID, Any] = {}
        for risk_item in reversed(risk_history_rows):
            history_by_id[risk_item.transaction_id] = _risk_activity(risk_item)
        for stored_item in reversed(stored_rows):
            history_by_id[stored_item.transaction_id] = _stored_activity(stored_item)
        for input_item in historical_input:
            if input_item.transaction_id not in history_by_id:
                history_by_id[input_item.transaction_id] = input_item
        history = list(history_by_id.values())

        candidates = _LegacyAlgorithm._detect(current=current, history=history)

        # Caller-supplied history seeds future baselines. Preserve rows already
        # captured by the anomaly activity table for any customer in this tenant.
        stored_history_ids: set[UUID] = set()
        if historical_ids:
            stored_history_ids = await self.repository.existing_activity_ids(
                historical_ids
            )

        additions: list[TransactionAnomalyActivity] = []
        for item in historical_input:
            if item.transaction_id in stored_history_ids:
                continue
            additions.append(
                TransactionAnomalyActivity(
                    tenant_id=self.tenant_id,
                    customer_id=payload.customer_id,
                    transaction_id=item.transaction_id,
                    amount=item.amount,
                    currency=item.currency,
                    destination_country=item.destination_country,
                    beneficiary_id=item.beneficiary_id,
                    transaction_type=item.transaction_type,
                    occurred_at=item.occurred_at,
                )
            )
        for item in current:
            additions.append(
                TransactionAnomalyActivity(
                    tenant_id=self.tenant_id,
                    customer_id=payload.customer_id,
                    transaction_id=item.transaction_id,
                    amount=item.amount,
                    currency=item.currency,
                    destination_country=item.destination_country,
                    beneficiary_id=item.beneficiary_id,
                    transaction_type=item.transaction_type,
                    occurred_at=item.occurred_at,
                )
            )
        self.repository.create_activities(additions)

        events = [
            TransactionAnomaly(
                tenant_id=self.tenant_id,
                customer_id=payload.customer_id,
                transaction_id=candidate["transaction_id"],
                anomaly_type=candidate["anomaly_type"],
                risk_score=Decimal(candidate["risk_score"]),
                risk_level=_risk_level(candidate["risk_score"]),
                summary=candidate["summary"],
                details=candidate["details"],
            )
            for candidate in candidates
        ]
        self.repository.create_anomalies(events)

        try:
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="One or more transaction IDs have already been recorded.",
            ) from exc

        for event in events:
            await self.db.refresh(event)

        message = (
            "Anomaly analysis completed; review the generated events."
            if events
            else "Analysis completed; no configured anomaly patterns were triggered."
        )
        return events, message

    async def list_anomalies(
        self, *, customer_id: UUID | None = None, limit: int = 100
    ) -> list[TransactionAnomaly]:
        return await self.repository.list_anomalies(
            customer_id=customer_id,
            limit=limit,
        )

    async def get_anomaly(self, anomaly_id: UUID) -> TransactionAnomaly:
        anomaly = await self.repository.get_anomaly(anomaly_id)
        if anomaly is None:
            raise not_found("Transaction anomaly")
        return anomaly
