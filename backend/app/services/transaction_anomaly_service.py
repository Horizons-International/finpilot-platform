"""Statistical transaction-anomaly detection with tenant-scoped history."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from statistics import median
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.transaction_anomaly import (
    TransactionAnomaly,
    TransactionAnomalyActivity,
)
from app.models.transaction_risk_analysis import TransactionRiskTransaction
from app.repositories.transaction_anomaly_repository import (
    TransactionAnomalyRepository,
)
from app.schemas.transaction_anomaly import (
    TransactionActivityInput,
    TransactionAnomalyAnalysisRequest,
)
from app.utils.date_time import utc_now
from app.utils.errors import not_found

_HISTORY_DAYS = 180
_MAX_STORED_HISTORY = 5000


@dataclass(frozen=True)
class _Activity:
    transaction_id: UUID
    amount: Decimal
    currency: str
    destination_country: str | None
    beneficiary_id: str | None
    transaction_type: str
    occurred_at: datetime


def _input_activity(item: TransactionActivityInput) -> _Activity:
    return _Activity(
        transaction_id=item.transaction_id,
        amount=item.amount,
        currency=item.currency,
        destination_country=item.destination_country,
        beneficiary_id=item.beneficiary_id,
        transaction_type=item.transaction_type,
        occurred_at=item.occurred_at,
    )


def _stored_activity(item: TransactionAnomalyActivity) -> _Activity:
    return _Activity(
        transaction_id=item.transaction_id,
        amount=item.amount,
        currency=item.currency,
        destination_country=(
            item.destination_country.strip().upper()
            if item.destination_country
            else None
        ),
        beneficiary_id=item.beneficiary_id,
        transaction_type=item.transaction_type,
        occurred_at=item.occurred_at,
    )


def _risk_activity(item: TransactionRiskTransaction) -> _Activity:
    return _Activity(
        transaction_id=item.transaction_id,
        amount=item.amount,
        currency=item.currency,
        destination_country=(
            item.destination_country.strip().upper()
            if item.destination_country
            else None
        ),
        beneficiary_id=None,
        transaction_type=item.transaction_type,
        occurred_at=item.occurred_at,
    )


def _risk_level(score: int) -> str:
    if score >= 85:
        return "CRITICAL"
    if score >= 70:
        return "HIGH"
    if score >= 40:
        return "MEDIUM"
    return "LOW"


def _positive_day_span(items: list[_Activity]) -> float:
    if len(items) < 2:
        return 1.0
    delta = max(item.occurred_at for item in items) - min(
        item.occurred_at for item in items
    )
    return max(1.0, delta.total_seconds() / 86400.0)


def _distance_hours(left: int, right: int) -> int:
    difference = abs(left - right)
    return min(difference, 24 - difference)


class TransactionAnomalyService:
    """Detect deviations from each customer's historical transaction activity."""

    def __init__(self, db: Session, tenant_id: UUID) -> None:
        self.db = db
        self.tenant_id = tenant_id
        active_tenant = db.info.get("tenant_id")
        if active_tenant is not None and active_tenant != tenant_id:
            raise ValueError("The session is already bound to another tenant.")
        db.info["tenant_id"] = tenant_id
        self.repository = TransactionAnomalyRepository(db, tenant_id=tenant_id)

    def analyze(
        self, payload: TransactionAnomalyAnalysisRequest
    ) -> tuple[list[TransactionAnomaly], str]:
        customer = self.repository.get_customer(payload.customer_id)
        if customer is None:
            raise not_found("Customer")

        current = [
            _input_activity(payload_item) for payload_item in payload.transactions
        ]
        current_ids = {item_current.transaction_id for item_current in current}
        historical_input = [
            _input_activity(transaction_item)
            for transaction_item in payload.historical_transactions
        ]
        historical_ids = {input_item.transaction_id for input_item in historical_input}
        if historical_ids:
            historical_activity_owners = self.repository.activity_for_transaction_ids(
                historical_ids
            )
            historical_risk_owners = self.repository.risk_transactions_for_ids(
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

        # IDs are unique within a tenant for this anomaly framework. Fail closed
        # if a current transaction has already been observed, including for a
        # different customer in the same tenant.
        already_observed = self.repository.activity_for_transaction_ids(current_ids)
        if already_observed:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="One or more transaction IDs have already been analyzed.",
            )

        risk_id_rows = self.repository.risk_transactions_for_ids(current_ids)
        if any(
            risk_row.customer_id != payload.customer_id for risk_row in risk_id_rows
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A transaction ID is already associated with another customer.",
            )

        cutoff = utc_now() - timedelta(days=_HISTORY_DAYS)
        stored_rows = self.repository.list_activity_history(
            payload.customer_id,
            cutoff=cutoff,
            excluded_ids=current_ids,
            limit=_MAX_STORED_HISTORY,
        )
        risk_rows = self.repository.list_risk_transaction_history(
            payload.customer_id,
            cutoff=cutoff,
            excluded_ids=current_ids,
            limit=_MAX_STORED_HISTORY,
        )

        history_by_id: dict[UUID, _Activity] = {}
        for risk_item in reversed(risk_rows):
            history_by_id[risk_item.transaction_id] = _risk_activity(risk_item)
        for stored_item in reversed(stored_rows):
            history_by_id[stored_item.transaction_id] = _stored_activity(stored_item)
        for historical_item in historical_input:
            if historical_item.transaction_id not in history_by_id:
                history_by_id[historical_item.transaction_id] = historical_item
        history = list(history_by_id.values())

        candidates = self._detect(current=current, history=history)

        # Request-supplied historical records seed future baselines as well as
        # this analysis. Skip IDs already persisted for any customer in tenant.
        stored_history_ids: set[UUID] = set()
        if historical_ids:
            stored_history_ids = self.repository.existing_activity_ids(historical_ids)
        additions: list[TransactionAnomalyActivity] = []
        for historical_item in historical_input:
            if historical_item.transaction_id in stored_history_ids:
                continue
            additions.append(
                TransactionAnomalyActivity(
                    tenant_id=self.tenant_id,
                    customer_id=payload.customer_id,
                    transaction_id=historical_item.transaction_id,
                    amount=historical_item.amount,
                    currency=historical_item.currency,
                    destination_country=historical_item.destination_country,
                    beneficiary_id=historical_item.beneficiary_id,
                    transaction_type=historical_item.transaction_type,
                    occurred_at=historical_item.occurred_at,
                )
            )
        for current_item in current:
            additions.append(
                TransactionAnomalyActivity(
                    tenant_id=self.tenant_id,
                    customer_id=payload.customer_id,
                    transaction_id=current_item.transaction_id,
                    amount=current_item.amount,
                    currency=current_item.currency,
                    destination_country=current_item.destination_country,
                    beneficiary_id=current_item.beneficiary_id,
                    transaction_type=current_item.transaction_type,
                    occurred_at=current_item.occurred_at,
                )
            )
        self.repository.create_activities(additions)

        events: list[TransactionAnomaly] = []
        for candidate in candidates:
            event = TransactionAnomaly(
                tenant_id=self.tenant_id,
                customer_id=payload.customer_id,
                transaction_id=candidate["transaction_id"],
                anomaly_type=candidate["anomaly_type"],
                risk_score=Decimal(candidate["risk_score"]),
                risk_level=_risk_level(candidate["risk_score"]),
                summary=candidate["summary"],
                details=candidate["details"],
            )
            events.append(event)

        self.repository.create_anomalies(events)
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="One or more transaction IDs have already been recorded.",
            ) from exc

        for event in events:
            self.db.refresh(event)
        message = (
            "Anomaly analysis completed; review the generated events."
            if events
            else "Analysis completed; no configured anomaly patterns were triggered."
        )
        return events, message

    @staticmethod
    def _detect(
        *, current: list[_Activity], history: list[_Activity]
    ) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        seen: set[tuple[UUID, str]] = set()

        def add(
            item: _Activity,
            anomaly_type: str,
            score: int,
            summary: str,
            details: dict[str, Any],
        ) -> None:
            key = (item.transaction_id, anomaly_type)
            if key in seen:
                return
            seen.add(key)
            candidates.append(
                {
                    "transaction_id": item.transaction_id,
                    "anomaly_type": anomaly_type,
                    "risk_score": score,
                    "summary": summary,
                    "details": details,
                }
            )

        history_by_currency: dict[str, list[_Activity]] = defaultdict(list)
        current_by_currency: dict[str, list[_Activity]] = defaultdict(list)
        for history_item in history:
            history_by_currency[history_item.currency].append(history_item)
        for currency_item in current:
            current_by_currency[currency_item.currency].append(currency_item)

        # Batch-level transaction-volume spike: compare the batch total with a
        # conservative expected amount over the observed window, in each currency.
        ordered_current = sorted(current, key=lambda item: item.occurred_at)
        window_seconds = max(
            3600.0,
            (
                max(item.occurred_at for item in current)
                - min(item.occurred_at for item in current)
            ).total_seconds(),
        )
        window_days = window_seconds / 86400.0
        for currency, batch in current_by_currency.items():
            baseline = history_by_currency.get(currency, [])
            if not baseline:
                continue
            baseline_total = sum((item.amount for item in baseline), Decimal("0"))
            baseline_span = _positive_day_span(baseline)
            expected_total = (
                baseline_total / Decimal(str(baseline_span)) * Decimal(str(window_days))
            )
            baseline_median = Decimal(str(median([item.amount for item in baseline])))
            batch_total = sum((item.amount for item in batch), Decimal("0"))
            threshold = max(
                expected_total * Decimal("3"),
                baseline_median * Decimal("5"),
            )
            if batch_total >= threshold:
                batch_ratio = (
                    float(batch_total / expected_total) if expected_total > 0 else 0.0
                )
                add(
                    ordered_current[0],
                    "TRANSACTION_VOLUME_SPIKE",
                    92 if batch_ratio >= 10 else 80,
                    (
                        f"The current {currency} batch total "
                        "materially exceeds the historical baseline."
                    ),
                    {
                        "currency": currency,
                        "current_batch_total": str(batch_total),
                        "expected_baseline_total": str(
                            expected_total.quantize(Decimal("0.01"))
                        ),
                        "historical_transaction_count": len(baseline),
                        "current_transaction_count": len(batch),
                        "comparison_window_hours": round(window_seconds / 3600.0, 2),
                    },
                )

        # Transaction frequency is measured by transaction count over a minimum
        # one-hour observation window, compared to the customer's historical rate.
        if history:
            expected_frequency = (
                len(history) / _positive_day_span(history) * window_days
            )
            frequency_threshold = max(5.0, expected_frequency * 3.0)
            if len(current) >= frequency_threshold:
                add(
                    ordered_current[0],
                    "UNUSUAL_TRANSACTION_FREQUENCY",
                    85 if len(current) >= 10 else 75,
                    (
                        "Transaction frequency is materially higher "
                        "than the available historical rate."
                    ),
                    {
                        "current_transaction_count": len(current),
                        "expected_count_for_window": round(expected_frequency, 3),
                        "comparison_window_hours": round(window_seconds / 3600.0, 2),
                        "historical_transaction_count": len(history),
                    },
                )

        historical_countries = {
            item.destination_country.strip().upper()
            for item in history
            if item.destination_country
        }
        historical_beneficiaries = {
            item.beneficiary_id for item in history if item.beneficiary_id
        }
        historical_hours = [item.occurred_at.hour for item in history]
        history_hours_are_meaningful = len(history) >= 5

        for current_item in current:
            baseline = history_by_currency.get(current_item.currency, [])
            if baseline:
                baseline_median = Decimal(str(median([row.amount for row in baseline])))
                ratio = (
                    current_item.amount / baseline_median
                    if baseline_median > 0
                    else Decimal("0")
                )
                if ratio >= Decimal("3"):
                    score = 85 if ratio >= Decimal("5") else 72
                    add(
                        current_item,
                        "UNUSUAL_TRANSACTION_AMOUNT",
                        score,
                        (
                            "The transaction amount is substantially larger "
                            "than this customer's historical amount for the "
                            "same currency."
                        ),
                        {
                            "currency": current_item.currency,
                            "transaction_amount": str(current_item.amount),
                            "historical_median_amount": str(baseline_median),
                            "amount_ratio": round(float(ratio), 2),
                            "historical_sample_count": len(baseline),
                        },
                    )

            country = (
                current_item.destination_country.strip().upper()
                if current_item.destination_country
                else None
            )
            if historical_countries and country and country not in historical_countries:
                add(
                    current_item,
                    "NEW_DESTINATION_COUNTRY",
                    70,
                    (
                        f"The transaction destination country {country} is"
                        " not present in supplied or retained historical activity."
                    ),
                    {
                        "destination_country": country,
                        "historical_destination_countries": sorted(
                            historical_countries
                        ),
                    },
                )

            if (
                current_item.beneficiary_id
                and historical_beneficiaries
                and current_item.beneficiary_id not in historical_beneficiaries
            ):
                add(
                    current_item,
                    "NEW_BENEFICIARY",
                    75,
                    (
                        "The beneficiary has not appeared in supplied"
                        " or retained historical activity."
                    ),
                    {
                        "beneficiary_id": current_item.beneficiary_id,
                        "known_historical_beneficiary_count": len(
                            historical_beneficiaries
                        ),
                    },
                )

            if history_hours_are_meaningful and historical_hours:
                min_hour_distance = min(
                    _distance_hours(current_item.occurred_at.hour, hour)
                    for hour in historical_hours
                )
                if min_hour_distance >= 4:
                    add(
                        current_item,
                        "UNUSUAL_TIMING",
                        60,
                        (
                            "The transaction time differs from the customer's "
                            "observed historical transaction hours."
                        ),
                        {
                            "transaction_hour_utc": current_item.occurred_at.hour,
                            "nearest_historical_hour_distance": min_hour_distance,
                            "historical_sample_count": len(history),
                        },
                    )

        return sorted(
            candidates,
            key=lambda row: (
                -row["risk_score"],
                str(row["transaction_id"]),
                row["anomaly_type"],
            ),
        )

    def list_anomalies(
        self, *, customer_id: UUID | None = None, limit: int = 100
    ) -> list[TransactionAnomaly]:
        return self.repository.list_anomalies(
            customer_id=customer_id,
            limit=limit,
        )

    def get_anomaly(self, anomaly_id: UUID) -> TransactionAnomaly:
        anomaly = self.repository.get_anomaly(anomaly_id)
        if anomaly is None:
            raise not_found("Transaction anomaly")
        return anomaly
