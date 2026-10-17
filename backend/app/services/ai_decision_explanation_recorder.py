"""Record explainability metadata in the same transaction as AI decisions.

A Session ``before_flush`` listener captures finalized decisions automatically.
This avoids making individual decision services responsible for a second write
and prevents a decision being committed without its accompanying explanation.
"""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from app.models.ai_decision_explanation import AIDecisionExplanation

_DECISION_TYPES: dict[str, str] = {
    "case_priorities": "CASE_PRIORITY",
    "ai_risk_recommendations": "AI_RISK_RECOMMENDATION",
    "transaction_risk_analyses": "TRANSACTION_RISK_ANALYSIS",
    "document_fraud_analyses": "DOCUMENT_FRAUD_ANALYSIS",
    "aml_investigation_analyses": "AML_INVESTIGATION_ANALYSIS",
    "ai_interactions": "AI_INTERACTION",
}
_RISK_KEYS = {
    "additional_risk_indicators",
    "risk_indicators",
    "risk_factors",
    "inconsistencies",
    "quality_issues",
    "quality_notes",
    "findings",
    "missing_documents",
    "missing_information",
    "duplicate_matches",
}


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if hasattr(value, "value"):
        return _json_safe(value.value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _confidence(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        confidence = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not confidence.is_finite() or confidence < 0 or confidence > 1:
        return None
    return confidence.quantize(Decimal("0.0001"))


def _factor(label: str, value: Any, **extra: Any) -> dict[str, Any]:
    result: dict[str, Any] = {"label": label, "value": _json_safe(value)}
    result.update({key: _json_safe(item) for key, item in extra.items()})
    return result


def _severity(score: float | int | None) -> str:
    if score is None:
        return "UNKNOWN"
    if score >= 75:
        return "CRITICAL"
    if score >= 50:
        return "HIGH"
    if score >= 25:
        return "MEDIUM"
    return "LOW"


def _append_id_source(
    target: list[dict[str, Any]], source_type: str, record_id: Any, **meta: Any
) -> None:
    if record_id:
        target.append(
            {
                "source_type": source_type,
                "record_id": str(record_id),
                **{key: _json_safe(value) for key, value in meta.items()},
            }
        )


def _sources_from_risk_snapshot(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    customer = _dict(snapshot.get("customer"))
    _append_id_source(
        sources,
        "customer_profile",
        customer.get("id") or snapshot.get("customer_id"),
        table="customers",
    )
    profile = _dict(snapshot.get("customer_risk_profile"))
    if profile:
        sources.append(
            {
                "source_type": "customer_risk_profile",
                "table": "customer_risk_profiles",
                "customer_id": customer.get("id") or snapshot.get("customer_id"),
                "risk_score": profile.get("risk_score"),
                "risk_level": profile.get("risk_level"),
            }
        )
    for item in _list(snapshot.get("transaction_analyses")):
        item_dict = _dict(item)
        _append_id_source(
            sources,
            "transaction_risk_analysis",
            item_dict.get("id"),
            table="transaction_risk_analyses",
            risk_score=item_dict.get("risk_score"),
        )
    alerts = _dict(snapshot.get("aml_alerts"))
    for item in _list(alerts.get("transaction_anomalies")):
        item_dict = _dict(item)
        _append_id_source(
            sources,
            "transaction_anomaly",
            item_dict.get("id"),
            table="transaction_anomalies",
            risk_score=item_dict.get("risk_score"),
        )
    for item in _list(alerts.get("matched_monitoring_results")):
        item_dict = _dict(item)
        _append_id_source(
            sources,
            "matched_monitoring_alert",
            item_dict.get("id"),
            table="transaction_monitoring_results",
            rule_id=item_dict.get("rule_id"),
        )
    for item in _list(snapshot.get("verification_results")):
        item_dict = _dict(item)
        _append_id_source(
            sources,
            "verification_result",
            item_dict.get("id"),
            table="identity_verification_cases",
            verification_type=item_dict.get("verification_type"),
            status=item_dict.get("status"),
        )
    for item in _list(snapshot.get("previous_compliance_cases")):
        item_dict = _dict(item)
        _append_id_source(
            sources,
            "previous_compliance_case",
            item_dict.get("id"),
            table="compliance_cases",
            priority=item_dict.get("priority"),
            status=item_dict.get("status"),
        )
    for item in _list(snapshot.get("document_analysis_results")):
        item_dict = _dict(item)
        _append_id_source(
            sources,
            "document_fraud_analysis",
            item_dict.get("id"),
            table="document_fraud_analyses",
            risk_score=item_dict.get("risk_score"),
        )
    selected_case = _dict(snapshot.get("selected_compliance_case"))
    _append_id_source(
        sources,
        "selected_compliance_case",
        selected_case.get("id"),
        table="compliance_cases",
    )
    return sources[:100]


def _sources_from_context(context: dict[str, Any]) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    known_id_fields = {
        "customer_id": ("customer", "customers"),
        "document_id": ("document", "customer_documents"),
        "verification_case_id": ("verification_case", "identity_verification_cases"),
        "case_id": ("compliance_case", "compliance_cases"),
        "analysis_id": ("analysis", "transaction_risk_analyses"),
        "transaction_id": ("transaction", "transaction_risk_transactions"),
    }

    def walk(value: Any, path: str = "context", depth: int = 0) -> None:
        if depth > 5 or not isinstance(value, dict):
            return
        for key, child in value.items():
            if key in known_id_fields and child:
                source_type, table = known_id_fields[key]
                _append_id_source(
                    sources,
                    source_type,
                    child,
                    table=table,
                    context_path=f"{path}.{key}",
                )
            source_keys = {
                "customer",
                "customer_profile",
                "document",
                "verification_case",
                "compliance_case",
            }
            if key in source_keys and isinstance(child, dict):
                nested_id = child.get("id")
                table_names = {
                    "customer": ("customer", "customers"),
                    "customer_profile": (
                        "customer_risk_profile",
                        "customer_risk_profiles",
                    ),
                    "document": ("document", "customer_documents"),
                    "verification_case": (
                        "verification_case",
                        "identity_verification_cases",
                    ),
                    "compliance_case": ("compliance_case", "compliance_cases"),
                }
                source_type, table = table_names[key]
                _append_id_source(
                    sources,
                    source_type,
                    nested_id,
                    table=table,
                    context_path=f"{path}.{key}",
                )
            if key == "knowledge_base":
                knowledge_base = _dict(child)
                for source in _list(knowledge_base.get("results")):
                    item = _dict(source)
                    _append_id_source(
                        sources,
                        "knowledge_document_chunk",
                        item.get("chunk_id"),
                        table="knowledge_document_chunks",
                        document_id=item.get("document_id"),
                        title=item.get("document_name"),
                        category=item.get("category"),
                        version=item.get("version"),
                        similarity=item.get("similarity"),
                    )
            if isinstance(child, dict):
                walk(child, f"{path}.{key}", depth + 1)
            elif isinstance(child, list) and key not in {"content", "excerpts"}:
                for index, item in enumerate(child[:50]):
                    if isinstance(item, dict):
                        walk(item, f"{path}.{key}[{index}]", depth + 1)

    walk(context)
    unique: dict[tuple[str, str], dict[str, Any]] = {}
    for source in sources:
        key = (str(source.get("source_type")), str(source.get("record_id")))
        unique[key] = source
    return list(unique.values())[:100]


def _result_factors(
    result: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    factors: list[dict[str, Any]] = []
    indicators: list[dict[str, Any]] = []
    for key, value in result.items():
        if key in {"summary", "confidence", "provider_name", "model_name"}:
            continue
        values = value if isinstance(value, list) else [value]
        for item in values[:30]:
            if item is None or item == "":
                continue
            if isinstance(item, dict):
                label = str(item.get("title") or item.get("code") or key)
                detail = item.get("description") or item.get("detail") or item
                entry = _factor(label, detail, category=key)
            else:
                entry = _factor(key.replace("_", " ").capitalize(), item, category=key)
            factors.append(entry)
            if key in _RISK_KEYS:
                indicators.append(entry)
    return factors[:100], indicators[:100]


def _build_payload(decision: Any, decision_type: str) -> dict[str, Any]:
    """Build an evidence-oriented explanation without calling an AI provider."""
    factors: list[dict[str, Any]] = []
    indicators: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    snapshot: dict[str, Any] = {}
    confidence: Decimal | None = None
    model_name = getattr(decision, "model_name", None) or getattr(
        decision, "model", None
    )
    provider_name = getattr(decision, "provider_name", None)
    reason = "The source decision did not provide a separate textual rationale."

    if decision_type == "CASE_PRIORITY":
        risk_snapshot = _dict(getattr(decision, "risk_snapshot", None))
        signals = _dict(risk_snapshot.get("signals"))
        weights = _dict(risk_snapshot.get("weights"))
        available_weight = sum(
            float(weights.get(key, 0.0))
            for key, value in signals.items()
            if value is not None
        )
        available_count = 0
        for name, raw_value in signals.items():
            weight = float(weights.get(name, 0.0))
            if raw_value is None:
                factors.append(
                    _factor(
                        name.replace("_", " ").capitalize(),
                        "unavailable",
                        weight=weight,
                    )
                )
                continue
            value = float(raw_value)
            available_count += 1
            contribution = (
                value * weight / available_weight if available_weight else 0.0
            )
            factor = _factor(
                name.replace("_", " ").capitalize(),
                value,
                scale="0-100",
                weight=weight,
                normalized_weighted_contribution=round(contribution, 4),
            )
            factors.append(factor)
            indicators.append(
                _factor(
                    name.replace("_", " ").capitalize(),
                    value,
                    severity=_severity(value),
                )
            )
        confidence = _confidence(available_count / max(1, len(weights)))
        sources = _sources_from_risk_snapshot(risk_snapshot)
        case_id = getattr(decision, "case_id", None)
        _append_id_source(sources, "compliance_case", case_id, table="compliance_cases")
        customer_id = risk_snapshot.get("customer_id")
        if risk_snapshot.get("customer_risk_score") is not None:
            sources.append(
                {
                    "source_type": "customer_risk_profile",
                    "table": "customer_risk_profiles",
                    "customer_id": customer_id,
                    "risk_score": risk_snapshot.get("customer_risk_score"),
                    "risk_level": risk_snapshot.get("customer_risk_level"),
                }
            )
        _append_id_source(
            sources,
            "transaction_anomaly",
            risk_snapshot.get("latest_anomaly_id"),
            table="transaction_anomalies",
            risk_score=risk_snapshot.get("latest_anomaly_score"),
        )
        _append_id_source(
            sources,
            "transaction_risk_analysis",
            risk_snapshot.get("latest_transaction_risk_analysis_id"),
            table="transaction_risk_analyses",
            risk_score=risk_snapshot.get("latest_transaction_risk_score"),
        )
        _append_id_source(
            sources,
            "transaction",
            risk_snapshot.get("latest_transaction_id"),
            table="transaction_anomaly_activity_or_risk_transactions",
            amount=risk_snapshot.get("latest_transaction_amount"),
            currency=risk_snapshot.get("latest_transaction_currency"),
        )
        if risk_snapshot.get("prior_case_count_sampled"):
            sources.append(
                {
                    "source_type": "previous_compliance_case_history",
                    "table": "compliance_cases",
                    "sampled_count": risk_snapshot.get("prior_case_count_sampled"),
                    "unresolved_count": risk_snapshot.get(
                        "prior_unresolved_case_count_sampled"
                    ),
                }
            )
        if risk_snapshot.get("latest_destination_country"):
            sources.append(
                {
                    "source_type": "transaction_geography",
                    "country": risk_snapshot.get("latest_destination_country"),
                    "geographic_signal": signals.get("geographic_risk"),
                }
            )
        reason = str(getattr(decision, "reason", "")) or reason
        snapshot = {
            "priority_level": _json_safe(getattr(decision, "priority_level", None)),
            "priority_score": _json_safe(getattr(decision, "priority_score", None)),
            "algorithm_version": risk_snapshot.get("algorithm_version"),
            "weights": weights,
            "confidence_method": "fraction of configured priority signals available",
        }
        model_name = risk_snapshot.get("algorithm_version") or "case-priority-v1"
        provider_name = "deterministic_rules"

    elif decision_type == "AI_RISK_RECOMMENDATION":
        risk_factors = _list(getattr(decision, "risk_factors", None))
        factors = [_factor("Risk factor", item) for item in risk_factors]
        indicators = list(factors)
        risk_snapshot = _dict(getattr(decision, "input_snapshot", None))
        sources = _sources_from_risk_snapshot(risk_snapshot)
        confidence = _confidence(getattr(decision, "confidence", None))
        reason = str(getattr(decision, "reason", "")) or reason
        recommendation = str(getattr(decision, "recommendation", ""))
        if recommendation:
            reason = f"{reason}\nRecommendation: {recommendation}"
        snapshot = {
            "risk_score": _json_safe(getattr(decision, "risk_score", None)),
            "risk_level": getattr(decision, "risk_level", None),
            "required_review_type": getattr(decision, "required_review_type", None),
            "suggested_action": getattr(decision, "suggested_action", None),
            "evidence_categories_available": sorted(risk_snapshot.keys()),
        }

    elif decision_type == "TRANSACTION_RISK_ANALYSIS":
        risk_factors = _list(getattr(decision, "risk_factors", None))
        factors = [_factor("Risk factor", item) for item in risk_factors]
        indicators = list(factors)
        context = _dict(getattr(decision, "context_snapshot", None))
        current_activity = _dict(context.get("current_activity"))
        if current_activity:
            factors.append(_factor("Current activity summary", current_activity))
        sources = _sources_from_context(context)
        customer_id = getattr(decision, "customer_id", None)
        _append_id_source(sources, "customer", customer_id, table="customers")
        for item in _list(context.get("current_transactions"))[:100]:
            row = _dict(item)
            _append_id_source(
                sources,
                "transaction",
                row.get("transaction_id"),
                table="transaction_risk_transactions",
                amount=row.get("amount"),
                currency=row.get("currency"),
            )
        confidence = _confidence(getattr(decision, "confidence", None))
        reason = str(getattr(decision, "reason", "")) or reason
        action = str(getattr(decision, "recommended_action", ""))
        if action:
            reason = f"{reason}\nRecommended action: {action}"
        snapshot = {
            "risk_score": _json_safe(getattr(decision, "risk_score", None)),
            "risk_level": getattr(decision, "risk_level", None),
            "transaction_summary": _json_safe(
                getattr(decision, "transaction_summary", {}) or {}
            ),
            "baseline_summary": _json_safe(
                getattr(decision, "baseline_summary", {}) or {}
            ),
        }

    elif decision_type == "DOCUMENT_FRAUD_ANALYSIS":
        result = _dict(getattr(decision, "result", None))
        factors, indicators = _result_factors(result)
        confidence = _confidence(result.get("confidence"))
        _append_id_source(
            sources,
            "customer_document",
            getattr(decision, "document_id", None),
            table="customer_documents",
        )
        _append_id_source(
            sources,
            "customer",
            getattr(decision, "customer_id", None),
            table="customers",
        )
        if getattr(decision, "requested_by", None):
            _append_id_source(
                sources,
                "requesting_user",
                getattr(decision, "requested_by", None),
                table="users",
            )
        status = str(getattr(decision, "status", "UNKNOWN"))
        score = getattr(decision, "risk_score", None)
        level = getattr(decision, "risk_level", None)
        overall_risk = _factor(
            "Document fraud risk",
            score,
            severity=str(
                level or _severity(float(score) if score is not None else None)
            ),
            needs_manual_review=bool(getattr(decision, "needs_manual_review", False)),
        )
        factors.insert(0, overall_risk)
        indicators.insert(0, overall_risk)
        reason_parts = [str(result.get("summary", "")).strip()]
        for field in ("recommended_actions", "suggested_actions"):
            actions = result.get(field)
            if isinstance(actions, list):
                reason_parts.extend(str(action) for action in actions[:5])
        if not any(reason_parts):
            manual_review = bool(getattr(decision, "needs_manual_review", False))
            reason_parts.append(
                f"Document fraud analysis risk score is {score} "
                f"({level or 'UNKNOWN'}); manual review required: {manual_review}."
            )
        reason = " ".join(part for part in reason_parts if part) or reason
        provider_name = getattr(decision, "provider_name", None)
        snapshot = {
            "status": status,
            "risk_score": _json_safe(score),
            "risk_level": level,
            "needs_manual_review": bool(
                getattr(decision, "needs_manual_review", False)
            ),
            "result_fields": sorted(result.keys()),
            "confidence_unavailable_reason": (
                "The document fraud result did not return a confidence score."
                if confidence is None
                else None
            ),
        }

    elif decision_type == "AML_INVESTIGATION_ANALYSIS":
        result = _dict(getattr(decision, "result", None))
        factors, indicators = _result_factors(result)
        confidence = _confidence(result.get("confidence"))
        source_context = _dict(getattr(decision, "source_context", None))
        sources = _sources_from_context(source_context)
        for source in _list(getattr(decision, "sources", None)):
            item = _dict(source)
            if item:
                sources.append(
                    {"source_type": "stored_investigation_source", **_json_safe(item)}
                )
        _append_id_source(
            sources,
            "customer",
            getattr(decision, "customer_id", None),
            table="customers",
        )
        _append_id_source(
            sources,
            "compliance_case",
            getattr(decision, "compliance_case_id", None),
            table="compliance_cases",
        )
        summary = str(result.get("summary", "")).strip()
        actions = result.get("suggested_actions")
        if isinstance(actions, list):
            summary = " ".join([summary, *[str(item) for item in actions[:5]]]).strip()
        reason = summary or reason
        provider_name = getattr(decision, "provider_name", None)
        model_name = getattr(decision, "model_name", None)
        snapshot = {
            "status": getattr(decision, "status", None),
            "result_fields": sorted(result.keys()),
            "question": str(getattr(decision, "question", ""))[:1000],
        }

    elif decision_type == "AI_INTERACTION":
        context = _dict(getattr(decision, "context", None))
        result = _dict(getattr(decision, "response_data", None))
        factors, indicators = _result_factors(result)
        sources = _sources_from_context(context)
        confidence_value = result.get("confidence")
        if confidence_value is None:
            nested_result = _dict(result.get("result"))
            confidence_value = nested_result.get("confidence")
        confidence = _confidence(confidence_value)
        answer = str(result.get("summary", "") or result.get("recommendation", ""))
        if not answer:
            answer = str(getattr(decision, "response_text", "") or "").strip()
        reason = answer[:5000] or reason
        _append_id_source(
            sources,
            "ai_prompt",
            getattr(decision, "prompt_id", None),
            table="ai_prompts",
            ai_function=_json_safe(getattr(decision, "ai_function", None)),
        )
        snapshot = {
            "ai_function": _json_safe(getattr(decision, "ai_function", None)),
            "resource_type": _json_safe(getattr(decision, "resource_type", None)),
            "resource_id": _json_safe(getattr(decision, "resource_id", None)),
            "status": _json_safe(getattr(decision, "status", None)),
            "response_fields": sorted(result.keys()),
        }

    # De-duplicate identical factors/sources without changing their order.
    seen_factors: set[str] = set()
    unique_factors: list[dict[str, Any]] = []
    for item in factors[:100]:
        marker = str(_json_safe(item))
        if marker not in seen_factors:
            seen_factors.add(marker)
            unique_factors.append(item)
    seen_sources: set[str] = set()
    unique_sources: list[dict[str, Any]] = []
    for item in sources[:100]:
        marker = str(_json_safe(item))
        if marker not in seen_sources:
            seen_sources.add(marker)
            unique_sources.append(item)

    if not indicators and unique_factors:
        indicators = unique_factors[:20]

    return {
        "tenant_id": getattr(decision, "tenant_id"),
        "decision_type": decision_type,
        "decision_id": getattr(decision, "id"),
        "factors": _json_safe(unique_factors),
        "data_sources": _json_safe(unique_sources),
        "risk_indicators": _json_safe(indicators[:100]),
        "confidence_score": confidence,
        "recommendation_reason": reason[:10000],
        "model_name": str(model_name)[:200] if model_name else None,
        "provider_name": str(provider_name)[:100] if provider_name else None,
        "decision_snapshot": _json_safe(snapshot),
    }


def _is_finalized(entity: Any, *, is_new: bool) -> bool:
    table = getattr(entity, "__tablename__", "")
    finalized_tables = {
        "document_fraud_analyses",
        "aml_investigation_analyses",
        "ai_interactions",
    }
    if table not in finalized_tables:
        return is_new
    status_value = getattr(entity, "status", "")
    status = str(
        status_value.value if hasattr(status_value, "value") else status_value
    ).upper()
    if status != "COMPLETED":
        return False
    if is_new:
        return True
    state = inspect(entity)
    status_history = state.attrs.status.history
    return status_history.has_changes() and status == "COMPLETED"


def _record_explanations(session: Session, flush_context: Any, instances: Any) -> None:
    del flush_context, instances
    new_entities = list(session.new)
    new_ids = {id(entity) for entity in new_entities}
    dirty_entities = [entity for entity in session.dirty if id(entity) not in new_ids]
    pending: list[AIDecisionExplanation] = []
    seen_keys: set[tuple[str, UUID]] = set()
    for entity in (*new_entities, *dirty_entities):
        table = getattr(entity, "__tablename__", "")
        decision_type = _DECISION_TYPES.get(table)
        if decision_type is None:
            continue
        is_new = id(entity) in new_ids
        if not _is_finalized(entity, is_new=is_new):
            continue
        decision_id = getattr(entity, "id", None)
        if decision_id is None:
            decision_id = uuid4()
            setattr(entity, "id", decision_id)
        if not isinstance(decision_id, UUID):
            continue
        key = (decision_type, decision_id)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        tenant_id = getattr(entity, "tenant_id", None)
        if not isinstance(tenant_id, UUID):
            raise ValueError(
                f"Cannot record {decision_type} explainability without a tenant UUID."
            )
        active_tenant_id = session.info.get("tenant_id")
        if active_tenant_id is not None and active_tenant_id != tenant_id:
            raise ValueError(
                "The decision tenant does not match the active database session."
            )
        payload = _build_payload(entity, decision_type)
        payload["id"] = uuid4()
        pending.append(AIDecisionExplanation(**payload))
    if pending:
        session.add_all(pending)


def install_ai_decision_explanation_recorder() -> None:
    """Install the automatic explainability recorder exactly once per process."""
    if not event.contains(Session, "before_flush", _record_explanations):
        event.listen(Session, "before_flush", _record_explanations)
