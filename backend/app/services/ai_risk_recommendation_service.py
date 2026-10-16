"""AI-assisted risk recommendations grounded in stored FinPilot risk evidence.

The deterministic floor prevents the AI model from reducing risk below verified
signals in FinPilot's own records. Recommendations are decision support and never
automatically close a case or take adverse action against a customer.
"""

import json
from decimal import Decimal
from time import monotonic
from typing import Any, cast
from uuid import UUID

from sqlalchemy.orm import Session

from app.ai.config import get_ai_config
from app.ai.providers.factory import get_ai_provider
from app.ai.schemas.requests import AIRequest, AIRequestType
from app.ai.services.ai_service import AIService
from app.core.logger import get_logger
from app.models.ai_risk_recommendation import AIRiskRecommendation
from app.models.compliance_case import ComplianceCase
from app.repositories.ai_risk_recommendation_repository import (
    AIRiskRecommendationRepository,
)
from app.schemas.ai_risk_recommendation import AIRiskRecommendationGenerateRequest
from app.schemas.transaction_risk_analysis import TransactionRiskAIOutput
from app.utils.errors import not_found

logger = get_logger(__name__)


def risk_level_for_score(score: int) -> str:
    """Translate a validated 0-100 score to FinPilot's standard risk bands."""
    if score >= 75:
        return "CRITICAL"
    if score >= 50:
        return "HIGH"
    if score >= 25:
        return "MEDIUM"
    return "LOW"


def required_review_type_for_score(score: int) -> str:
    if score >= 75:
        return "URGENT_COMPLIANCE_REVIEW"
    if score >= 50:
        return "ENHANCED_DUE_DILIGENCE"
    if score >= 25:
        return "STANDARD_COMPLIANCE_REVIEW"
    return "ROUTINE_MONITORING"


def suggested_action_for_score(score: int) -> str:
    """Return a conservative action aligned to the final policy risk band."""
    if score >= 75:
        return (
            "Escalate to a senior compliance officer; conduct enhanced due diligence, "
            "review source of funds and beneficiary details, and document the "
            "disposition of every open alert before the case is resolved."
        )
    if score >= 50:
        return (
            "Perform an enhanced review of transaction activity, verify source of "
            "funds and beneficiary details, and document the disposition of relevant "
            "AML alerts."
        )
    if score >= 25:
        return (
            "Review the identified indicators and verification/document findings; "
            "request clarification where evidence is incomplete and record the "
            "review outcome."
        )
    return (
        "Continue routine monitoring and reassess if material new alerts, transaction "
        "changes, or verification findings arise."
    )


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return max(0, min(100, int(Decimal(str(value)))))
    except (ValueError, TypeError, ArithmeticError):
        return default


def calculate_deterministic_risk(snapshot: dict[str, Any]) -> tuple[int, list[str]]:
    """Compute a transparent minimum score from existing, trusted risk records."""
    scores: list[int] = []
    factors: list[str] = []

    customer = snapshot.get("customer") or {}
    customer_status = str(customer.get("status", "")).upper()
    if customer_status in {"SUSPENDED", "REJECTED"}:
        scores.append(70)
        factors.append(f"Customer status requires review: {customer_status}.")

    profile = snapshot.get("customer_risk_profile") or {}
    if profile.get("risk_score") is not None:
        scores.append(_as_int(profile.get("risk_score")))
        factors.append(
            "Existing customer risk profile: "
            f"{profile.get('risk_level', 'UNKNOWN')} "
            f"(score {profile.get('risk_score')})."
        )

    transaction_analyses = snapshot.get("transaction_analyses", [])
    for index, analysis in enumerate(transaction_analyses):
        # Use the most recent transaction assessment as the numeric signal, while
        # retaining the older assessments as explanatory history in the snapshot.
        if index == 0:
            scores.append(_as_int(analysis.get("risk_score")))
        factors.extend(str(item) for item in analysis.get("risk_factors", []) if item)
        if analysis.get("reason"):
            factors.append(f"Transaction-risk analysis: {analysis['reason']}")

    anomalies = snapshot.get("aml_alerts", {}).get("transaction_anomalies", [])
    for anomaly in anomalies:
        scores.append(_as_int(anomaly.get("risk_score")))
        label = anomaly.get("anomaly_type") or "transaction anomaly"
        summary = anomaly.get("summary")
        factors.append(f"AML anomaly {label}: {summary or 'recorded in FinPilot'}")

    matched_alerts = snapshot.get("aml_alerts", {}).get(
        "matched_monitoring_results", []
    )
    alert_count = len(matched_alerts)
    if alert_count:
        # One match warrants review; repeated matches raise the deterministic floor.
        scores.append(min(95, 55 + (alert_count - 1) * 10))
        factors.append(f"{alert_count} matched AML monitoring alert(s) are recorded.")

    seen_verification_types: set[str] = set()
    for result in snapshot.get("verification_results", []):
        verification_type = str(result.get("verification_type", "UNKNOWN"))
        if verification_type in seen_verification_types:
            continue
        seen_verification_types.add(verification_type)
        status = str(result.get("status", "")).upper()
        if status in {"REJECTED", "EXPIRED"}:
            scores.append(65)
            factors.append(
                f"Verification result requires follow-up for {verification_type}: "
                f"{status}."
            )
        elif status in {"PENDING", "UNDER_REVIEW", "NOT_STARTED"}:
            scores.append(35)
            factors.append(
                f"Latest {verification_type} verification is incomplete: {status}."
            )

    for case in snapshot.get("previous_compliance_cases", []):
        case_status = str(case.get("status", "")).upper()
        priority = str(case.get("priority", "")).upper()
        case_type = str(case.get("case_type", "")).upper()
        if case_status not in {"RESOLVED", "CLOSED"}:
            priority_scores = {"LOW": 30, "MEDIUM": 50, "HIGH": 70, "CRITICAL": 85}
            scores.append(priority_scores.get(priority, 35))
            factors.append(
                f"An unresolved compliance case exists ({case_type or 'case'}, "
                f"priority {priority or 'UNKNOWN'})."
            )

    seen_documents: set[str] = set()
    for analysis in snapshot.get("document_analysis_results", []):
        document_id = str(analysis.get("document_id", ""))
        if document_id in seen_documents:
            continue
        seen_documents.add(document_id)
        score = _as_int(analysis.get("risk_score"))
        scores.append(score)
        if score >= 25 or analysis.get("needs_manual_review"):
            factors.append(
                "Latest document analysis identified review concerns "
                f"(risk level {analysis.get('risk_level', 'UNKNOWN')}, score {score})."
            )
        if analysis.get("needs_manual_review"):
            scores.append(55)

    transaction_summaries = snapshot.get("transaction_analyses", [])
    residence = str((snapshot.get("customer") or {}).get("country_of_residence") or "")
    residence_normalized = residence.strip().casefold()
    for analysis in transaction_summaries:
        destinations = (analysis.get("transaction_summary") or {}).get(
            "destination_counts", {}
        )
        if residence_normalized and isinstance(destinations, dict):
            international = [
                str(country)
                for country in destinations
                if str(country).strip().casefold() != residence_normalized
            ]
            if international:
                scores.append(40)
                factors.append(
                    "Transaction analysis includes destination countries different "
                    "from the customer's recorded country of residence; verify context."
                )
            break

    if not factors:
        factors.append(
            "No material risk indicators were present in the available stored records; "
            "confirm that all relevant bank feeds have been ingested."
        )

    # Do not assume an absence of records proves an absence of risk.
    aml_alerts = snapshot.get("aml_alerts", {})
    has_evidence = bool(
        snapshot.get("customer_risk_profile")
        or snapshot.get("transaction_analyses")
        or aml_alerts.get("transaction_anomalies")
        or aml_alerts.get("matched_monitoring_results")
        or snapshot.get("verification_results")
        or snapshot.get("previous_compliance_cases")
        or snapshot.get("document_analysis_results")
    )
    if not has_evidence:
        scores.append(25)
        factors.append(
            "Risk context is incomplete; a standard compliance review is prudent."
        )

    score = max(scores, default=25)
    deduplicated = list(dict.fromkeys(factors))
    return score, deduplicated[:30]


def _enum_value(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


def _date_value(value: Any) -> str | None:
    if value is not None and hasattr(value, "isoformat"):
        return cast(str, value.isoformat())
    return None


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "value"):
        return value.value
    return value


class AIRiskRecommendationService:
    """Create durable recommendations from tenant-scoped source evidence."""

    def __init__(self, db: Session, *, tenant_id: UUID) -> None:
        active_tenant_id = db.info.get("tenant_id")
        if active_tenant_id is not None and active_tenant_id != tenant_id:
            raise ValueError("The database session is bound to another tenant.")
        db.info["tenant_id"] = tenant_id
        self.db = db
        self.tenant_id = tenant_id
        self.repository = AIRiskRecommendationRepository(db, tenant_id)

    def _build_snapshot(
        self, customer_id: UUID, selected_case: ComplianceCase | None
    ) -> dict[str, Any]:
        customer = self.repository.get_customer(customer_id)
        if customer is None:
            raise not_found("Customer")

        profile = self.repository.get_risk_profile(customer_id)
        transaction_analyses = self.repository.list_transaction_analyses(customer_id)
        anomalies = self.repository.list_anomalies(customer_id)
        matched_alerts = self.repository.list_aml_alerts(customer_id)
        verification_rows = self.repository.list_verification_results(customer_id)
        previous_cases = self.repository.list_previous_cases(customer_id)
        document_analyses = self.repository.list_document_analyses(customer_id)

        def risk_profile_dict() -> dict[str, Any] | None:
            if profile is None:
                return None
            return {
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
            "customer_risk_profile": risk_profile_dict(),
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
            # These standard keys allow FinPilot's existing mock AI provider to
            # produce structured output without adding a new provider contract.
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

    def generate(
        self,
        payload: AIRiskRecommendationGenerateRequest,
        *,
        user_id: UUID,
    ) -> AIRiskRecommendation:
        customer = self.repository.get_customer(payload.customer_id)
        if customer is None:
            raise not_found("Customer")

        selected_case = None
        if payload.compliance_case_id is not None:
            selected_case = self.repository.get_compliance_case(
                payload.compliance_case_id, payload.customer_id
            )
            if selected_case is None:
                # Avoid confirming whether another tenant owns a case identifier.
                raise not_found("Compliance case")

        snapshot = self._build_snapshot(payload.customer_id, selected_case)
        deterministic_score, deterministic_factors = calculate_deterministic_risk(
            snapshot
        )
        ai_result: TransactionRiskAIOutput | None = None
        provider_name = "deterministic_rules"
        model_name: str | None = None
        start = monotonic()

        ai_context = self._transaction_ai_context(snapshot)
        prompt = (
            "You are a compliance decision-support assistant. Analyze only the "
            "following tenant-scoped source evidence. Do not invent facts, infer "
            "guilt, "
            "or recommend an adverse action without human review. Return a risk score "
            "from 0 to 100, a concise evidence-grounded reason, an appropriate "
            "recommended action, risk factors, and confidence from 0 to 1. Consider "
            "the customer risk profile, prior transaction analysis, AML alerts, "
            "verification outcomes, previous compliance cases, and document fraud "
            "analysis. The score is advisory and must not be lower than a verified "
            "high-severity signal when that signal is present.\n\n"
            "TRANSACTION_RISK_CONTEXT_JSON:\n"
            + json.dumps(ai_context, ensure_ascii=False, separators=(",", ":"))
        )
        try:
            response = AIService(provider=get_ai_provider()).generate(
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
            # Preserve the deterministic evidence-based result if AI is not configured
            # or unavailable. The fallback is visible in provider_name and confidence.
            logger.warning(
                "AI risk recommendation used deterministic fallback: %s",
                type(exc).__name__,
            )

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
            customer_id=customer.id,
            compliance_case_id=(
                selected_case.id if selected_case is not None else None
            ),
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
        record = self.repository.create(record)
        self.db.commit()
        self.db.refresh(record)
        logger.info(
            "AI risk recommendation persisted: recommendation_id=%s tenant_id=%s "
            "customer_id=%s risk_level=%s duration_ms=%s",
            record.id,
            self.tenant_id,
            customer.id,
            risk_level,
            int((monotonic() - start) * 1000),
        )
        return record

    def get_recommendation(self, recommendation_id: UUID) -> AIRiskRecommendation:
        result = self.repository.get_recommendation(recommendation_id)
        if result is None:
            raise not_found("AI risk recommendation")
        return result

    def list_history(
        self,
        *,
        customer_id: UUID | None = None,
        compliance_case_id: UUID | None = None,
        limit: int = 50,
    ) -> list[AIRiskRecommendation]:
        if (
            customer_id is not None
            and self.repository.get_customer(customer_id) is None
        ):
            raise not_found("Customer")
        if compliance_case_id is not None:
            # When a customer filter was also supplied, ensure the case is linked to it.
            if customer_id is not None:
                case = self.repository.get_compliance_case(
                    compliance_case_id, customer_id
                )
            else:
                case = self.repository.get_compliance_case_by_id(compliance_case_id)
            if case is None:
                raise not_found("Compliance case")
        return self.repository.list_history(
            customer_id=customer_id,
            compliance_case_id=compliance_case_id,
            limit=limit,
        )
