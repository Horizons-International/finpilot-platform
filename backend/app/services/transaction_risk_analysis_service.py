"""AI-assisted AML risk review built on tenant-owned transaction facts."""

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.ai.providers.factory import get_ai_provider
from app.ai.schemas.requests import AIRequest, AIRequestType
from app.ai.schemas.responses import AIResponse
from app.ai.services.ai_service import AIService
from app.models.ai_usage_log import AIUsageLog
from app.models.customer import Customer
from app.models.transaction_risk_analysis import (
    TransactionRiskAnalysis,
    TransactionRiskTransaction,
)
from app.repositories.ai_usage_log_repository import AIUsageLogRepository
from app.repositories.transaction_risk_analysis_repository import (
    TransactionRiskAnalysisRepository,
)
from app.schemas.compliance_case import ComplianceCaseCreate
from app.schemas.transaction_risk_analysis import (
    TransactionRiskAIOutput,
    TransactionRiskAnalysisRequest,
)
from app.services.audit_service import AuditService
from app.services.compliance_service import ComplianceService
from app.services.subscription_service import record_subscription_usage
from app.utils.date_time import utc_now
from app.utils.enums import (
    AuditEventType,
    ComplianceCasePriority,
    ComplianceCaseType,
)
from app.utils.errors import not_found

_CONTEXT_MARKER = "TRANSACTION_RISK_CONTEXT_JSON:\n"


class TransactionRiskAnalysisService:
    """Create risk explanations and preserve each analysis for future review."""

    def __init__(self, db: Session, tenant_id: UUID) -> None:
        current_tenant_id = db.info.get("tenant_id")
        if current_tenant_id is not None and current_tenant_id != tenant_id:
            raise ValueError("The database session is bound to another tenant.")
        db.info["tenant_id"] = tenant_id
        self.db = db
        self.tenant_id = tenant_id
        self.repository = TransactionRiskAnalysisRepository(db, tenant_id=tenant_id)
        self.ai_usage_repository = AIUsageLogRepository(db, tenant_id=tenant_id)
        self.audit_service = AuditService(db)

    @staticmethod
    def _model_value(value: Any) -> Any:
        return value.value if hasattr(value, "value") else value

    @staticmethod
    def _observation_dict(item: Any) -> dict[str, Any]:
        if hasattr(item, "model_dump"):
            return cast(dict[str, Any], item.model_dump(mode="json"))
        return {
            "transaction_id": str(item.transaction_id),
            "amount": str(item.amount),
            "currency": item.currency,
            "destination_country": item.destination_country,
            "transaction_type": item.transaction_type,
            "occurred_at": item.occurred_at.isoformat(),
        }

    @staticmethod
    def _summary(transactions: list[dict[str, Any]]) -> dict[str, Any]:
        totals: dict[str, Decimal] = {}
        counts: dict[str, int] = {}
        destinations: dict[str, int] = {}
        types: dict[str, int] = {}
        for item in transactions:
            currency = str(item["currency"])
            amount = Decimal(str(item["amount"]))
            totals[currency] = totals.get(currency, Decimal("0")) + amount
            counts[currency] = counts.get(currency, 0) + 1
            destination = str(item["destination_country"])
            destinations[destination] = destinations.get(destination, 0) + 1
            transaction_type = str(item["transaction_type"])
            types[transaction_type] = types.get(transaction_type, 0) + 1
        average = {
            currency: str(
                (totals[currency] / counts[currency]).quantize(Decimal("0.01"))
            )
            for currency in totals
        }
        timestamp_pairs = [
            (
                datetime.fromisoformat(
                    str(item["occurred_at"]).replace("Z", "+00:00")
                ).astimezone(timezone.utc),
                str(item["occurred_at"]),
            )
            for item in transactions
        ]
        times = [
            value for _, value in sorted(timestamp_pairs, key=lambda pair: pair[0])
        ]
        counts_by_day: dict[str, int] = {}
        counts_by_hour_utc: dict[str, int] = {}
        for timestamp, _ in timestamp_pairs:
            day_key = timestamp.date().isoformat()
            hour_key = f"{timestamp.hour:02d}"
            counts_by_day[day_key] = counts_by_day.get(day_key, 0) + 1
            counts_by_hour_utc[hour_key] = counts_by_hour_utc.get(hour_key, 0) + 1
        return {
            "transaction_count": len(transactions),
            "total_by_currency": {
                key: str(value.quantize(Decimal("0.01")))
                for key, value in totals.items()
            },
            "average_amount_by_currency": average,
            "destination_counts": destinations,
            "transaction_type_counts": types,
            "transaction_counts_by_utc_day": counts_by_day,
            "transaction_counts_by_utc_hour": counts_by_hour_utc,
            "first_occurred_at": times[0] if times else None,
            "last_occurred_at": times[-1] if times else None,
        }

    def _customer_context(self, customer: Customer) -> dict[str, Any]:
        risk_profile = self.repository.get_risk_profile(customer.id)
        verification_rows = self.repository.list_verification_cases(
            customer.id,
            limit=100,
        )
        previous_cases = self.repository.list_compliance_cases(
            customer.id,
            limit=20,
        )
        return {
            "customer_id": str(customer.id),
            "risk_level": (
                self._model_value(risk_profile.risk_level)
                if risk_profile
                else "UNKNOWN"
            ),
            "risk_score": risk_profile.risk_score if risk_profile else None,
            "location": customer.country_of_residence,
            "customer_status": self._model_value(customer.status),
            "verification_statuses": [
                self._model_value(row.status) for row in verification_rows
            ],
            "verification_case_count": len(verification_rows),
            "previous_compliance_case_count": len(previous_cases),
            "previous_cases": [
                {
                    "case_id": str(case.id),
                    "case_type": self._model_value(case.case_type),
                    "priority": self._model_value(case.priority),
                    "status": self._model_value(case.status),
                    "created_at": (
                        case.created_at.isoformat() if case.created_at else None
                    ),
                }
                for case in previous_cases
            ],
        }

    def _historical_transactions(
        self,
        customer_id: UUID,
        payload: TransactionRiskAnalysisRequest,
    ) -> list[dict[str, Any]]:
        current_start = min(item.occurred_at for item in payload.transactions)
        window_start = current_start - timedelta(days=90)
        stored = self.repository.list_historical_transactions(
            customer_id,
            start_at=window_start,
            end_at=current_start,
            limit=1000,
        )
        candidates = [
            historical_item
            for historical_item in payload.historical_transactions
            if window_start <= historical_item.occurred_at < current_start
        ]
        combined: dict[str, dict[str, Any]] = {}
        for stored_item in stored:
            item_dict = self._observation_dict(stored_item)
            combined[item_dict["transaction_id"]] = item_dict
        for candidates_item in candidates:
            item_dict = self._observation_dict(candidates_item)
            combined[item_dict["transaction_id"]] = item_dict
        return sorted(combined.values(), key=lambda item: str(item["occurred_at"]))

    @staticmethod
    def _risk_level(score: int) -> str:
        if score >= 85:
            return "CRITICAL"
        if score >= 70:
            return "HIGH"
        if score >= 40:
            return "MEDIUM"
        return "LOW"

    def analyze(
        self,
        payload: TransactionRiskAnalysisRequest,
        *,
        user_id: UUID,
        email: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> TransactionRiskAnalysis:
        customer = self.repository.get_customer(payload.customer_id)
        if customer is None:
            raise not_found("Customer")

        incoming_ids = [item.transaction_id for item in payload.transactions]
        existing_ids = self.repository.get_existing_transaction_ids(incoming_ids)
        if existing_ids:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "One or more transaction IDs have already been analyzed "
                    "for this organization. Submit only new transaction IDs."
                ),
            )

        current_transactions = [
            self._observation_dict(item) for item in payload.transactions
        ]
        historical_transactions = self._historical_transactions(customer.id, payload)
        current_summary = self._summary(current_transactions)
        baseline_summary = self._summary(historical_transactions)
        customer_context = self._customer_context(customer)
        context = {
            "customer": customer_context,
            "historical_activity_90_days": baseline_summary,
            "current_activity": current_summary,
            "current_transactions": current_transactions,
            "historical_transactions": historical_transactions,
            "assessment_window_days": 90,
            "important_limitations": [
                "Historical data is limited to the supplied baseline "
                "and previously analyzed transactions stored here.",
                "Amounts in different currencies are not added together or converted.",
                "A risk score is a review signal, not proof of wrongdoing.",
            ],
        }
        prompt = (
            "You are an AML transaction-risk decision-support assistant. "
            "Analyze the current activity against the historical "
            "baseline and customer context. Return only the required "
            "structured fields: risk_score (integer 0-100), reason, "
            "recommended_action, "
            "risk_factors (array of concise "
            "evidence-based strings), and confidence (0-1). Explain "
            "measurable deviations such as changes in transaction count, "
            "value, timing, destinations, or types. Do not invent facts, "
            "claim that a customer committed a crime, or treat missing "
            "data as proof of risk. If there is insufficient history, say so and "
            "reduce confidence. A high score recommends human review only; "
            "do not recommend an automatic account freeze. Use an action "
            "proportionate to the evidence.\n\n"
            + _CONTEXT_MARKER
            + json.dumps(context, separators=(",", ":"), default=str)
        )

        # Consume the subscription allowance before invoking the provider, so an
        # over-quota request cannot still incur model cost or persist an analysis.
        record_subscription_usage(self.db, self.tenant_id, "ai_requests")
        provider = get_ai_provider()
        provider_config = getattr(provider, "config", None)
        model_name = getattr(provider_config, "model", None)
        started_at = utc_now()
        response: AIResponse = AIService(provider=provider).generate(
            AIRequest(
                request_type=AIRequestType.TRANSACTION_RISK_ANALYSIS,
                prompt=prompt,
                customer_id=customer.id,
                structured=True,
            )
        )
        elapsed_ms = max(0, int((utc_now() - started_at).total_seconds() * 1000))
        if response.structured_data is None:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=(
                    "The AI provider did not return structured transaction-risk data."
                ),
            )
        try:
            ai_result = TransactionRiskAIOutput.model_validate(response.structured_data)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=(
                    "The AI provider returned an invalid transaction-risk response."
                ),
            ) from exc

        risk_level = self._risk_level(ai_result.risk_score)
        analysis = TransactionRiskAnalysis(
            tenant_id=self.tenant_id,
            customer_id=customer.id,
            created_by=user_id,
            risk_score=ai_result.risk_score,
            risk_level=risk_level,
            reason=ai_result.reason,
            recommended_action=ai_result.recommended_action,
            risk_factors=ai_result.risk_factors,
            confidence=ai_result.confidence,
            provider_name=response.provider_name,
            model_name=model_name,
            context_snapshot=context,
            transaction_summary=current_summary,
            baseline_summary=baseline_summary,
            ai_response=ai_result.model_dump(mode="json"),
        )
        self.repository.create(analysis)
        transactions = [
            TransactionRiskTransaction(
                tenant_id=self.tenant_id,
                analysis_id=analysis.id,
                customer_id=customer.id,
                transaction_id=item.transaction_id,
                amount=item.amount,
                currency=item.currency,
                destination_country=item.destination_country,
                transaction_type=item.transaction_type,
                occurred_at=item.occurred_at,
            )
            for item in payload.transactions
        ]
        self.repository.create_transactions(transactions)
        self.ai_usage_repository.stage(
            AIUsageLog(
                tenant_id=self.tenant_id,
                user_id=user_id,
                feature="TRANSACTION_RISK_ANALYSIS",
                model=response.provider_name,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                response_time=elapsed_ms,
                error_message=None,
            )
        )
        self.audit_service.log_event(
            event_type=AuditEventType.AI_TRANSACTION_RISK_ANALYZED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="transaction_risk_analysis",
            resource_id=analysis.id,
        )
        self.db.flush()

        if ai_result.risk_score >= 70:
            case_priority = (
                ComplianceCasePriority.CRITICAL
                if ai_result.risk_score >= 85
                else ComplianceCasePriority.HIGH
            )
            case_description = (
                f"AI transaction-risk analysis {analysis.id} produced a "
                f"{risk_level} risk score of {ai_result.risk_score}/100. "
                f"Reason: {ai_result.reason}\nRecommended action: "
                f"{ai_result.recommended_action}\nThis is an AI-generated review "
                "signal and requires independent human assessment."
            )[:10000]
            case = ComplianceService(self.db, self.tenant_id).create_case(
                ComplianceCaseCreate(
                    customer_id=customer.id,
                    case_type=ComplianceCaseType.AML_ALERT,
                    priority=case_priority,
                    description=case_description,
                ),
                user_id=user_id,
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            analysis.compliance_case_id = case.id
            self.db.commit()
        else:
            self.db.commit()

        self.db.refresh(analysis)
        return analysis

    def get_analysis(self, analysis_id: UUID) -> TransactionRiskAnalysis:
        analysis = self.repository.get_analysis(analysis_id)
        if analysis is None:
            raise not_found("Transaction risk analysis")
        return analysis

    def list_analyses(
        self,
        *,
        customer_id: UUID | None = None,
        limit: int = 100,
    ) -> list[TransactionRiskAnalysis]:
        return self.repository.list_analyses(
            customer_id=customer_id,
            limit=limit,
        )
