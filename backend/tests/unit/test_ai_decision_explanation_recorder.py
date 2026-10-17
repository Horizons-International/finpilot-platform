from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from app.models.ai_decision_explanation import AIDecisionExplanation
from app.services.ai_decision_explanation_recorder import (
    _build_payload,
    _record_explanations,
)


def test_case_priority_explanation_preserves_signal_weights_and_confidence() -> None:
    tenant_id = uuid4()
    case_id = uuid4()
    priority = SimpleNamespace(
        __tablename__="case_priorities",
        id=uuid4(),
        tenant_id=tenant_id,
        case_id=case_id,
        priority_level="HIGH",
        priority_score=72.5,
        reason="Customer and transaction signals require review.",
        risk_snapshot={
            "algorithm_version": "case-priority-v1",
            "customer_id": str(uuid4()),
            "latest_anomaly_id": str(uuid4()),
            "signals": {
                "alert_severity": 70.0,
                "customer_risk": 80.0,
                "transaction_risk": None,
                "transaction_amount": None,
                "previous_history": 50.0,
                "geographic_risk": None,
            },
            "weights": {
                "alert_severity": 0.25,
                "customer_risk": 0.20,
                "transaction_risk": 0.25,
                "transaction_amount": 0.15,
                "previous_history": 0.10,
                "geographic_risk": 0.05,
            },
        },
    )

    payload = _build_payload(priority, "CASE_PRIORITY")

    assert payload["tenant_id"] == tenant_id
    assert payload["decision_id"] == priority.id
    assert payload["confidence_score"] == 0.5
    assert payload["model_name"] == "case-priority-v1"
    assert any(item["label"] == "Customer risk" for item in payload["factors"])
    assert any(
        item["source_type"] == "transaction_anomaly" for item in payload["data_sources"]
    )
    assert payload["recommendation_reason"] == priority.reason


def test_risk_recommendation_explanation_has_factors_sources_confidence() -> None:
    recommendation = SimpleNamespace(
        __tablename__="ai_risk_recommendations",
        id=uuid4(),
        tenant_id=uuid4(),
        risk_score=82,
        risk_level="CRITICAL",
        recommendation="Escalate for enhanced due diligence.",
        reason="A rejected verification and unresolved alert require review.",
        suggested_action="Conduct enhanced due diligence.",
        required_review_type="URGENT_COMPLIANCE_REVIEW",
        risk_factors=["Verification result requires follow-up.", "Open AML alert."],
        confidence=0.88,
        input_snapshot={
            "customer": {"id": str(uuid4()), "status": "PENDING_VERIFICATION"},
            "customer_risk_profile": {"risk_score": 73, "risk_level": "HIGH"},
            "transaction_analyses": [{"id": str(uuid4()), "risk_score": 82}],
            "aml_alerts": {
                "transaction_anomalies": [],
                "matched_monitoring_results": [],
            },
            "verification_results": [],
            "previous_compliance_cases": [],
            "document_analysis_results": [],
        },
        provider_name="mock",
        model_name="mock-model",
    )

    payload = _build_payload(recommendation, "AI_RISK_RECOMMENDATION")

    assert payload["confidence_score"] == Decimal("0.8800")
    assert payload["provider_name"] == "mock"
    assert len(payload["factors"]) == 2
    assert any(
        item["source_type"] == "transaction_risk_analysis"
        for item in payload["data_sources"]
    )
    assert "Recommendation:" in payload["recommendation_reason"]


def test_document_explanation_does_not_fabricate_missing_confidence() -> None:
    document_decision = SimpleNamespace(
        __tablename__="document_fraud_analyses",
        id=uuid4(),
        tenant_id=uuid4(),
        document_id=uuid4(),
        customer_id=uuid4(),
        requested_by=None,
        status="COMPLETED",
        risk_score=68,
        risk_level="HIGH",
        needs_manual_review=True,
        result={
            "summary": "The document contains discrepancies.",
            "inconsistencies": ["Document name differs from customer profile."],
            "recommended_actions": ["Review the original document."],
        },
        provider_name="mock",
        model_name=None,
    )

    payload = _build_payload(document_decision, "DOCUMENT_FRAUD_ANALYSIS")

    assert payload["confidence_score"] is None
    assert any(
        "Document name differs" in str(item) for item in payload["risk_indicators"]
    )
    assert payload["decision_snapshot"]["confidence_unavailable_reason"]
    assert payload["recommendation_reason"]


def test_before_flush_recorder_stages_explanation_with_decision() -> None:
    class FakeSession:
        def __init__(self, entity: object) -> None:
            self.new = [entity]
            self.dirty: set[object] = set()
            self.info = {"tenant_id": getattr(entity, "tenant_id")}
            self.staged: list[object] = []

        def add_all(self, values: list[object]) -> None:
            self.staged.extend(values)

    decision = SimpleNamespace(
        __tablename__="case_priorities",
        id=uuid4(),
        tenant_id=uuid4(),
        case_id=uuid4(),
        priority_level="MEDIUM",
        priority_score=51,
        reason="Alert severity is elevated.",
        risk_snapshot={
            "signals": {"alert_severity": 45.0},
            "weights": {"alert_severity": 0.25},
        },
    )
    session = FakeSession(decision)

    _record_explanations(session, None, None)  # type: ignore[arg-type]

    assert len(session.staged) == 1
    explanation = session.staged[0]
    assert isinstance(explanation, AIDecisionExplanation)
    assert explanation.decision_type == "CASE_PRIORITY"
    assert explanation.decision_id == decision.id
    assert explanation.tenant_id == decision.tenant_id
