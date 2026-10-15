import uuid

from app.ai.exceptions import AIProviderError
from app.ai.providers.base import AIProvider
from app.ai.schemas.config import AIConfig
from app.ai.schemas.requests import AIRequest, AIRequestType
from app.ai.schemas.responses import AIResponse


class MockAIProvider(AIProvider):
    def __init__(self, config: AIConfig) -> None:
        self.config = config

    def generate(self, request: AIRequest) -> AIResponse:
        if not request.prompt.strip():
            raise AIProviderError("AI prompt cannot be empty.")

        if request.request_type == AIRequestType.TEXT:
            return AIResponse(
                provider_name=self.config.provider,
                request_type=request.request_type.value,
                content=f"Mock AI response for: {request.prompt}",
                request_id=uuid.uuid4(),
                input_tokens=0,
                output_tokens=0,
            )

        if request.request_type == AIRequestType.DOCUMENT_ANALYSIS:
            if request.document_id is None:
                raise AIProviderError("Document ID is required for document analysis.")

            return AIResponse(
                provider_name=self.config.provider,
                request_type=request.request_type.value,
                content="Mock document analysis completed.",
                structured_data={
                    "document_id": str(request.document_id),
                    "document_type": "unknown",
                    "confidence": 0.0,
                },
                request_id=uuid.uuid4(),
                input_tokens=0,
                output_tokens=0,
            )

        if request.request_type == AIRequestType.COMPLIANCE_ASSISTANT:
            return AIResponse(
                provider_name=self.config.provider,
                request_type=request.request_type.value,
                content="Mock compliance assistant response.",
                structured_data={
                    "summary": "Mock compliance summary.",
                    "customer_status": "Pending",
                    "missing_documents": [],
                    "findings": [],
                    "recommendation": "Review the available compliance information.",
                    "confidence": 0.0,
                },
                request_id=uuid.uuid4(),
                input_tokens=0,
                output_tokens=0,
            )

        if request.request_type == AIRequestType.ANALYTICS_ASSISTANT:
            return AIResponse(
                provider_name=self.config.provider,
                request_type=request.request_type.value,
                content="Mock analytics assistant response.",
                structured_data={
                    "summary": "Mock analytics summary.",
                    "suggested_insights": [
                        "Mock analytics insight.",
                    ],
                    "confidence": 0.0,
                },
                request_id=uuid.uuid4(),
                input_tokens=0,
                output_tokens=0,
            )

        if request.request_type == AIRequestType.TRANSACTION_RISK_ANALYSIS:
            import json
            from decimal import Decimal

            marker = "TRANSACTION_RISK_CONTEXT_JSON:\n"
            try:
                context_text = request.prompt.split(marker, 1)[1]
                context = json.loads(context_text)
                current = context.get("current_activity", {})
                baseline = context.get("historical_activity_90_days", {})
                current_totals = current.get("total_by_currency", {})
                baseline_totals = baseline.get("total_by_currency", {})
                ratios = []
                for currency, current_total in current_totals.items():
                    prior_total = Decimal(str(baseline_totals.get(currency, "0")))
                    current_value = Decimal(str(current_total))
                    if prior_total > 0:
                        ratios.append(float(current_value / prior_total))
                ratio = max(ratios, default=0.0)
                count = int(current.get("transaction_count", 0))
                total_value = max(
                    (Decimal(str(value)) for value in current_totals.values()),
                    default=Decimal("0"),
                )
                if ratio >= 5 or (count >= 10 and total_value >= Decimal("20000")):
                    score = 92
                    reason = (
                        "Current transaction value or frequency materially"
                        " exceeds the available historical baseline."
                    )
                    action = (
                        "Manual compliance review and verification of source of funds."
                    )
                    factors = [
                        "Material deviation from historical"
                        " transaction value or frequency."
                    ]
                    confidence = 0.88 if baseline.get("transaction_count", 0) else 0.55
                elif ratio >= 2 or count >= 8:
                    score = 58
                    reason = (
                        "Current activity shows a moderate "
                        "deviation or elevated transaction frequency."
                    )
                    action = (
                        "Review the recent activity and continue enhanced monitoring."
                    )
                    factors = [
                        "Elevated transaction frequency or "
                        "value relative to available context."
                    ]
                    confidence = 0.62 if baseline.get("transaction_count", 0) else 0.4
                else:
                    score = 25
                    reason = (
                        "The development mock provider found "
                        "no strong deviation in the supplied sample."
                    )
                    action = "Continue routine monitoring and review material changes."
                    factors = [
                        "This is an illustrative mock-provider "
                        "assessment, not a production risk decision."
                    ]
                    confidence = 0.25
            except Exception:
                score = 35
                reason = (
                    "The development mock provider could "
                    "not derive a baseline from the supplied context."
                )
                action = "Review the transaction details manually."
                factors = ["Insufficient analyzable context in the mock provider."]
                confidence = 0.2
            return AIResponse(
                provider_name=self.config.provider,
                request_type=request.request_type.value,
                content=reason,
                structured_data={
                    "risk_score": score,
                    "reason": reason,
                    "recommended_action": action,
                    "risk_factors": factors,
                    "confidence": confidence,
                },
                request_id=uuid.uuid4(),
                input_tokens=0,
                output_tokens=0,
            )

        if request.request_type == AIRequestType.AML_INVESTIGATION_ASSISTANT:
            return AIResponse(
                provider_name=self.config.provider,
                request_type=request.request_type.value,
                content="Mock AML investigation review completed.",
                structured_data={
                    "summary": "Investigation assistance is ready for human review.",
                    "customer_overview": (
                        "Mock customer overview based on supplied source context."
                    ),
                    "risk_indicators": [],
                    "related_activity": [],
                    "suggested_actions": [
                        "Review the cited customer, case, and transaction records.",
                        "Verify material indicators before making an "
                        "investigative decision.",
                    ],
                    "confidence": 0.0,
                },
                request_id=uuid.uuid4(),
                input_tokens=0,
                output_tokens=0,
            )

        raise AIProviderError(f"Unsupported AI request type: {request.request_type}")
