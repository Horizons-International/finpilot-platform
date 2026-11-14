"""Native-async AI-assisted recommendations from stored risk evidence."""

import json
from decimal import Decimal
from time import monotonic
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.config import get_ai_config
from app.ai.providers.async_factory import get_async_ai_provider
from app.ai.schemas.requests import AIRequest, AIRequestType
from app.ai.services.async_ai_service import AsyncAIService
from app.core.logger import get_logger
from app.models.ai_risk_recommendation import AIRiskRecommendation
from app.models.audit_event import AuditEvent
from app.models.compliance_case import ComplianceCase
from app.repositories.async_ai_risk_recommendation_repository import (
    AsyncAIRiskRecommendationRepository,
)
from app.repositories.async_tenant_scoped_repository import resolve_async_tenant_id
from app.schemas.ai_risk_recommendation import AIRiskRecommendationGenerateRequest
from app.schemas.transaction_risk_analysis import TransactionRiskAIOutput
from app.services.ai_risk_recommendation_service import (
    _as_int,
    _date_value,
    _enum_value,
    _json_safe,
    calculate_deterministic_risk,
    required_review_type_for_score,
    risk_level_for_score,
    suggested_action_for_score,
)
from app.services.audit_event_service import sanitize_audit_metadata
from app.utils.errors import not_found

logger = get_logger(__name__)


class AsyncAIRiskRecommendationService:
    """Build a tenant-scoped snapshot and generate a conservative recommendation."""

    def __init__(self, db: AsyncSession, *, tenant_id: UUID) -> None:
        resolved_tenant_id = resolve_async_tenant_id(db, tenant_id)
        assert resolved_tenant_id is not None
        db.info["tenant_id"] = resolved_tenant_id
        self.db = db
        self.tenant_id = resolved_tenant_id
        self.repository = AsyncAIRiskRecommendationRepository(
            db, tenant_id=resolved_tenant_id
        )

    async def _build_snapshot(
        self, customer_id: UUID, selected_case: ComplianceCase | None
    ) -> dict[str, Any]:
        customer = await self.repository.get_customer(customer_id)
        if customer is None:
            raise not_found("Customer")

        profile = await self.repository.get_risk_profile(customer_id)
        transaction_analyses = await self.repository.list_transaction_analyses(
            customer_id
        )
        anomalies = await self.repository.list_anomalies(customer_id)
        matched_alerts = await self.repository.list_aml_alerts(customer_id)
        verification_rows = await self.repository.list_verification_results(customer_id)
        previous_cases = await self.repository.list_previous_cases(customer_id)
        document_analyses = await self.repository.list_document_analyses(customer_id)

        profile_snapshot: dict[str, Any] | None = None
        if profile is not None:
            profile_snapshot = {
                "risk_level": _enum_value(profile.risk_level),
                "risk_score": _as_int(profile.risk_score),
                "risk_category": profile.risk_category,
                "assessed_at": _date_value(profile.assessed_at),
                "assessment_source": profile.assessment_source,
            }

        snapshot: dict[str, Any] = {
            "customer": {
                "id": str(customer.id),
                "status": _enum_value(customer.status),
                "country_of_residence": customer.country_of_residence,
                "nationality": customer.nationality,
            },
            "customer_risk_profile": profile_snapshot,
            "transaction_analyses": [
                {
                    "id": str(row.id),
                    "risk_score": _as_int(row.risk_score),
                    "risk_level": row.risk_level,
                    "reason": row.reason,
                    "recommended_action": row.recommended_action,
                    "risk_factors": list(row.risk_factors or []),
                    "confidence": float(row.confidence or 0),
                    "transaction_summary": _json_safe(row.transaction_summary or {}),
                    "baseline_summary": _json_safe(row.baseline_summary or {}),
                    "created_at": _date_value(row.created_at),
                }
                for row in transaction_analyses
            ],
            "aml_alerts": {
                "transaction_anomalies": [
                    {
                        "id": str(row.id),
                        "anomaly_type": row.anomaly_type,
                        "risk_score": _as_int(row.risk_score),
                        "risk_level": row.risk_level,
                        "summary": row.summary,
                        "details": _json_safe(row.details or {}),
                        "created_at": _date_value(row.created_at),
                    }
                    for row in anomalies
                ],
                "matched_monitoring_results": [
                    {
                        "id": str(row.id),
                        "transaction_id": str(row.transaction_id),
                        "rule_id": str(row.rule_id),
                        "result": _enum_value(row.result),
                        "country": row.country,
                        "created_at": _date_value(row.created_at),
                    }
                    for row in matched_alerts
                ],
            },
            "verification_results": [
                {
                    "id": str(row.id),
                    "verification_type": _enum_value(row.verification_type),
                    "status": _enum_value(row.status),
                    "created_at": _date_value(row.created_at),
                    "completed_at": _date_value(row.completed_at),
                }
                for row in verification_rows
            ],
            "previous_compliance_cases": [
                {
                    "id": str(row.id),
                    "case_type": _enum_value(row.case_type),
                    "priority": _enum_value(row.priority),
                    "status": _enum_value(row.status),
                    "description": (row.description or "")[:1000],
                    "created_at": _date_value(row.created_at),
                }
                for row in previous_cases
            ],
            "document_analysis_results": [
                {
                    "id": str(row.id),
                    "document_id": str(row.document_id),
                    "risk_score": _as_int(row.risk_score),
                    "risk_level": row.risk_level,
                    "needs_manual_review": bool(row.needs_manual_review),
                    "status": row.status,
                    "result": _json_safe(row.result or {}),
                    "created_at": _date_value(row.created_at),
                }
                for row in document_analyses
            ],
            "selected_compliance_case": (
                {
                    "id": str(selected_case.id),
                    "case_type": _enum_value(selected_case.case_type),
                    "priority": _enum_value(selected_case.priority),
                    "status": _enum_value(selected_case.status),
                }
                if selected_case is not None
                else None
            ),
        }
        return cast(dict[str, Any], _json_safe(snapshot))

    @staticmethod
    def _transaction_ai_context(snapshot: dict[str, Any]) -> dict[str, Any]:
        analyses = snapshot.get("transaction_analyses", [])
        latest = analyses[0] if analyses else {}
        current = latest.get("transaction_summary", {})
        baseline = latest.get("baseline_summary", {})
        return {
            "current_activity": {
                "transaction_count": int(current.get("transaction_count", 0) or 0),
                "total_by_currency": current.get("total_by_currency", {}),
                "destination_counts": current.get("destination_counts", {}),
            },
            "historical_activity_90_days": {
                "transaction_count": int(baseline.get("transaction_count", 0) or 0),
                "total_by_currency": baseline.get("total_by_currency", {}),
                "destination_counts": baseline.get("destination_counts", {}),
            },
            "risk_evidence": snapshot,
        }

    async def generate(
        self,
        payload: AIRiskRecommendationGenerateRequest,
        *,
        user_id: UUID,
    ) -> AIRiskRecommendation:
        customer = await self.repository.get_customer(payload.customer_id)
        if customer is None:
            raise not_found("Customer")

        selected_case: ComplianceCase | None = None
        if payload.compliance_case_id is not None:
            selected_case = await self.repository.get_compliance_case(
                payload.compliance_case_id, payload.customer_id
            )
            if selected_case is None:
                # Avoid disclosing whether an identifier belongs to a different tenant.
                raise not_found("Compliance case")

        selected_case_id = selected_case.id if selected_case is not None else None
        snapshot = await self._build_snapshot(payload.customer_id, selected_case)
        # No ORM instances are used after this point. End the read transaction
        # before waiting on the external AI provider.
        await self.db.rollback()
        deterministic_score, deterministic_factors = calculate_deterministic_risk(
            snapshot
        )
        ai_result: TransactionRiskAIOutput | None = None
        provider_name = "deterministic_rules"
        model_name: str | None = None
        started_at = monotonic()
        response_time_ms = 0

        ai_context = self._transaction_ai_context(snapshot)
        prompt = (
            "You are a compliance decision-support assistant. Analyze only the "
            "following tenant-scoped source evidence. Do not invent facts, infer "
            "guilt, or recommend an adverse action without human review. Return a "
            "risk score from 0 to 100, a concise evidence-grounded reason, an "
            "appropriate recommended action, risk factors, and confidence from 0 "
            "to 1. Consider the customer risk profile, prior transaction analysis, "
            "AML alerts, verification outcomes, previous compliance cases, and "
            "document fraud analysis. The score is advisory and must not be lower "
            "than a verified high-severity signal when that signal is present.\n\n"
            "TRANSACTION_RISK_CONTEXT_JSON:\n"
            + json.dumps(ai_context, ensure_ascii=False, separators=(",", ":"))
        )
        try:
            async with AsyncAIService(provider=get_async_ai_provider()) as ai_service:
                response = await ai_service.generate(
                    AIRequest(
                        request_type=AIRequestType.TRANSACTION_RISK_ANALYSIS,
                        prompt=prompt,
                        customer_id=payload.customer_id,
                        structured=True,
                    )
                )
            if response.structured_data is None:
                raise ValueError("AI provider returned no structured recommendation.")
            ai_result = TransactionRiskAIOutput.model_validate(response.structured_data)
            provider_name = response.provider_name
            model_name = get_ai_config().model or None
        except Exception as exc:
            # Keep the deterministic evidence floor usable when AI is offline or
            # returns invalid data. The source snapshot remains available for review.
            logger.warning(
                "AI risk recommendation used deterministic fallback: %s",
                type(exc).__name__,
            )
        finally:
            response_time_ms = max(0, int((monotonic() - started_at) * 1000))

        final_score = max(
            deterministic_score,
            ai_result.risk_score if ai_result is not None else 0,
        )
        risk_level = risk_level_for_score(final_score)
        review_type = required_review_type_for_score(final_score)
        policy_action = suggested_action_for_score(final_score)
        ai_factors = ai_result.risk_factors if ai_result is not None else []
        risk_factors = list(dict.fromkeys([*deterministic_factors, *ai_factors]))[:30]
        if ai_result is None or ai_result.risk_score < deterministic_score:
            recommendation_text = policy_action
        else:
            recommendation_text = ai_result.recommended_action

        if ai_result is not None:
            reason_text = ai_result.reason.strip()
            confidence = float(ai_result.confidence)
        else:
            reason_text = (
                "Recommendation generated from stored FinPilot risk evidence using "
                "deterministic fallback rules because structured AI output was "
                "unavailable."
            )
            confidence = 0.25

        if deterministic_factors:
            evidence_text = "Evidence considered: " + " ".join(
                deterministic_factors[:8]
            )
            if evidence_text not in reason_text:
                reason_text = f"{reason_text}\n\n{evidence_text}"

        record = AIRiskRecommendation(
            tenant_id=self.tenant_id,
            customer_id=payload.customer_id,
            compliance_case_id=selected_case_id,
            created_by=user_id,
            risk_score=Decimal(final_score).quantize(Decimal("0.01")),
            risk_level=risk_level,
            recommendation=recommendation_text,
            reason=reason_text,
            suggested_action=policy_action,
            required_review_type=review_type,
            risk_factors=risk_factors,
            confidence=confidence,
            input_snapshot=snapshot,
            provider_name=provider_name,
            model_name=model_name,
        )
        record = await self.repository.create_recommendation(record)
        self.db.add(
            AuditEvent(
                tenant_id=self.tenant_id,
                user_id=user_id,
                action="AI_RECOMMENDATION_CREATED",
                entity_type="ai_risk_recommendation",
                entity_id=record.id,
                event_metadata=sanitize_audit_metadata(
                    {
                        "customer_id": str(record.customer_id),
                        "risk_level": record.risk_level,
                        "provider_name": provider_name,
                        "response_time_ms": response_time_ms,
                    }
                ),
            )
        )
        await self.db.flush()
        await self.db.commit()
        await self.db.refresh(record)
        logger.info(
            "AI risk recommendation persisted: recommendation_id=%s tenant_id=%s "
            "customer_id=%s risk_level=%s duration_ms=%s",
            record.id,
            self.tenant_id,
            payload.customer_id,
            risk_level,
            response_time_ms,
        )
        return record

    async def get_recommendation(self, recommendation_id: UUID) -> AIRiskRecommendation:
        result = await self.repository.get_recommendation(recommendation_id)
        if result is None:
            raise not_found("AI risk recommendation")
        return result

    async def list_history(
        self,
        *,
        customer_id: UUID | None = None,
        compliance_case_id: UUID | None = None,
        limit: int = 50,
    ) -> tuple[list[AIRiskRecommendation], int]:
        if (
            customer_id is not None
            and await self.repository.get_customer(customer_id) is None
        ):
            raise not_found("Customer")
        if compliance_case_id is not None:
            if customer_id is not None:
                case = await self.repository.get_compliance_case(
                    compliance_case_id, customer_id
                )
            else:
                case = await self.repository.get_compliance_case_by_id(
                    compliance_case_id
                )
            if case is None:
                raise not_found("Compliance case")
        items = await self.repository.list_history(
            customer_id=customer_id,
            compliance_case_id=compliance_case_id,
            limit=limit,
        )
        total = await self.repository.count_history(
            customer_id=customer_id,
            compliance_case_id=compliance_case_id,
        )
        return items, total
