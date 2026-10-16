"""Explainable, tenant-scoped compliance case prioritization.

The model is deliberately deterministic: each score can be explained from a
stored snapshot of the source signals, and an LLM cannot silently invent a
risk value or take an adverse action.
"""

from decimal import ROUND_HALF_UP, Decimal
from statistics import median
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.case_priority import CasePriority
from app.models.compliance_case import ComplianceCase
from app.models.customer import Customer
from app.models.customer_risk_profile import CustomerRiskProfile
from app.models.system_configuration import SystemConfiguration
from app.models.transaction_anomaly import (
    TransactionAnomaly,
    TransactionAnomalyActivity,
)
from app.models.transaction_risk_analysis import (
    TransactionRiskAnalysis,
    TransactionRiskTransaction,
)
from app.repositories.tenant_scoped_repository import resolve_tenant_id
from app.services.tenant_access_audit import deny_tenant_access
from app.utils.enums import (
    ComplianceCasePriority,
    ComplianceCaseStatus,
    SystemConfigurationCategory,
    SystemConfigurationStatus,
)

ALGORITHM_VERSION = "case-priority-v1"
PRIORITY_SCORE_BY_ALERT_LEVEL: dict[ComplianceCasePriority, float] = {
    ComplianceCasePriority.LOW: 20.0,
    ComplianceCasePriority.MEDIUM: 45.0,
    ComplianceCasePriority.HIGH: 70.0,
    ComplianceCasePriority.CRITICAL: 95.0,
}
PRIORITY_WEIGHTS: dict[str, float] = {
    "alert_severity": 0.25,
    "customer_risk": 0.20,
    "transaction_risk": 0.25,
    "transaction_amount": 0.15,
    "previous_history": 0.10,
    "geographic_risk": 0.05,
}


def priority_level_for_score(score: float) -> ComplianceCasePriority:
    if score >= 85:
        return ComplianceCasePriority.CRITICAL
    if score >= 65:
        return ComplianceCasePriority.HIGH
    if score >= 40:
        return ComplianceCasePriority.MEDIUM
    return ComplianceCasePriority.LOW


def calculate_priority_score(signals: dict[str, float | None]) -> float:
    """Return a weighted mean over available signals, omitting missing data.

    Alert severity is always available. Missing customer/transaction/history
    evidence does not get silently treated as a zero-risk signal.
    """
    weighted_total = 0.0
    total_weight = 0.0
    for name, weight in PRIORITY_WEIGHTS.items():
        signal = signals.get(name)
        if signal is None:
            continue
        bounded = max(0.0, min(100.0, float(signal)))
        weighted_total += bounded * weight
        total_weight += weight
    if total_weight <= 0:
        return 0.0
    return round(weighted_total / total_weight, 2)


class CasePriorityService:
    def __init__(self, db: Session, tenant_id: UUID) -> None:
        self.db = db
        resolved = resolve_tenant_id(db, tenant_id)
        assert resolved is not None
        self.tenant_id = resolved

    def _get_case(self, case_id: UUID) -> ComplianceCase:
        case = (
            self.db.query(ComplianceCase)
            .filter(
                ComplianceCase.id == case_id,
                ComplianceCase.tenant_id == self.tenant_id,
            )
            .first()
        )
        if case is None:
            deny_tenant_access(
                self.db,
                resource_type="compliance_case",
                resource_id=case_id,
                resource_name="Compliance case",
            )
        return case

    @staticmethod
    def _enum_value(value: Any) -> str | None:
        if value is None:
            return None
        return str(value.value if hasattr(value, "value") else value)

    def _high_risk_countries(self) -> set[str]:
        """Read high-risk geography only from a tenant-owned risk configuration."""
        configurations = (
            self.db.query(SystemConfiguration)
            .filter(
                SystemConfiguration.tenant_id == self.tenant_id,
                SystemConfiguration.category == SystemConfigurationCategory.RISK,
                SystemConfiguration.status == SystemConfigurationStatus.ACTIVE,
            )
            .all()
        )
        countries: set[str] = set()
        for item in configurations:
            value = item.value if isinstance(item.value, dict) else {}
            configured: Any = value.get("high_risk_countries")
            if configured is None and "high_risk_country" in item.key.lower():
                configured = value.get("countries", value.get("country", []))
            if isinstance(configured, str):
                configured = [configured]
            if isinstance(configured, list):
                countries.update(
                    str(country).strip().casefold()
                    for country in configured
                    if str(country).strip()
                )
        return countries

    def _snapshot_and_score(
        self, case: ComplianceCase
    ) -> tuple[dict[str, Any], float, str]:
        customer = (
            self.db.query(Customer)
            .filter(
                Customer.id == case.customer_id,
                Customer.tenant_id == self.tenant_id,
            )
            .first()
        )
        if customer is None:
            # A case/customer mismatch should fail closed rather than silently
            # produce a score based on incomplete cross-tenant context.
            deny_tenant_access(
                self.db,
                resource_type="customer",
                resource_id=case.customer_id,
                resource_name="Customer",
            )

        profile = (
            self.db.query(CustomerRiskProfile)
            .filter(
                CustomerRiskProfile.customer_id == customer.id,
                CustomerRiskProfile.tenant_id == self.tenant_id,
            )
            .first()
        )
        latest_anomaly = (
            self.db.query(TransactionAnomaly)
            .filter(
                TransactionAnomaly.customer_id == customer.id,
                TransactionAnomaly.tenant_id == self.tenant_id,
            )
            .order_by(TransactionAnomaly.created_at.desc())
            .first()
        )
        case_linked_analysis = (
            self.db.query(TransactionRiskAnalysis)
            .filter(
                TransactionRiskAnalysis.customer_id == customer.id,
                TransactionRiskAnalysis.tenant_id == self.tenant_id,
                TransactionRiskAnalysis.compliance_case_id == case.id,
            )
            .order_by(TransactionRiskAnalysis.created_at.desc())
            .first()
        )
        latest_analysis = case_linked_analysis or (
            self.db.query(TransactionRiskAnalysis)
            .filter(
                TransactionRiskAnalysis.customer_id == customer.id,
                TransactionRiskAnalysis.tenant_id == self.tenant_id,
            )
            .order_by(TransactionRiskAnalysis.created_at.desc())
            .first()
        )

        activity_rows = (
            self.db.query(TransactionAnomalyActivity)
            .filter(
                TransactionAnomalyActivity.customer_id == customer.id,
                TransactionAnomalyActivity.tenant_id == self.tenant_id,
            )
            .order_by(TransactionAnomalyActivity.occurred_at.desc())
            .limit(200)
            .all()
        )
        risk_transaction_rows = (
            self.db.query(TransactionRiskTransaction)
            .filter(
                TransactionRiskTransaction.customer_id == customer.id,
                TransactionRiskTransaction.tenant_id == self.tenant_id,
            )
            .order_by(TransactionRiskTransaction.occurred_at.desc())
            .limit(200)
            .all()
        )

        prior_cases = (
            self.db.query(ComplianceCase)
            .filter(
                ComplianceCase.tenant_id == self.tenant_id,
                ComplianceCase.customer_id == customer.id,
                ComplianceCase.id != case.id,
            )
            .order_by(ComplianceCase.created_at.desc())
            .limit(100)
            .all()
        )
        unresolved_statuses = {
            ComplianceCaseStatus.OPEN,
            ComplianceCaseStatus.ASSIGNED,
            ComplianceCaseStatus.UNDER_REVIEW,
            ComplianceCaseStatus.ESCALATED,
        }
        unresolved_count = sum(
            1 for prior in prior_cases if prior.status in unresolved_statuses
        )
        history_score: float | None = (
            min(100.0, len(prior_cases) * 8.0 + unresolved_count * 15.0)
            if prior_cases
            else None
        )

        # Prefer transaction facts tied to this case. Otherwise use the most
        # recent tenant-scoped activity for this customer as contextual evidence.
        recent_transactions: list[Any] = []
        if case_linked_analysis is not None:
            recent_transactions = (
                self.db.query(TransactionRiskTransaction)
                .filter(
                    TransactionRiskTransaction.tenant_id == self.tenant_id,
                    TransactionRiskTransaction.analysis_id == case_linked_analysis.id,
                    TransactionRiskTransaction.customer_id == customer.id,
                )
                .order_by(TransactionRiskTransaction.occurred_at.desc())
                .all()
            )
        if not recent_transactions:
            combined: dict[UUID, Any] = {}
            for risk_transaction in risk_transaction_rows:
                combined[risk_transaction.transaction_id] = risk_transaction
            for activity_transaction in activity_rows:
                combined[activity_transaction.transaction_id] = activity_transaction
            recent_transactions = sorted(
                combined.values(),
                key=lambda item: item.occurred_at,
                reverse=True,
            )
        latest_transaction = recent_transactions[0] if recent_transactions else None

        amount_signal: float | None = None
        amount_ratio: float | None = None
        if latest_transaction is not None:
            amount = Decimal(str(latest_transaction.amount))
            currency = str(latest_transaction.currency).upper()
            baseline_amounts: list[Decimal] = []
            rows = [activity_row for activity_row in activity_rows] + [
                risk_row for risk_row in risk_transaction_rows
            ]
            for transaction in rows:
                if (
                    transaction.transaction_id != latest_transaction.transaction_id
                    and str(transaction.currency).upper() == currency
                    and Decimal(str(transaction.amount)) > 0
                ):
                    baseline_amounts.append(Decimal(str(transaction.amount)))
            if baseline_amounts:
                baseline_median = Decimal(str(median(baseline_amounts)))
                if baseline_median > 0:
                    amount_ratio = float(amount / baseline_median)
                    if amount_ratio >= 5:
                        amount_signal = 100.0
                    elif amount_ratio >= 2.5:
                        amount_signal = 80.0
                    elif amount_ratio >= 1.5:
                        amount_signal = 60.0
                    else:
                        amount_signal = 25.0

        home_country = (customer.country_of_residence or "").strip()
        destination_country = (
            str(latest_transaction.destination_country or "").strip()
            if latest_transaction is not None
            else ""
        )
        geographic_signal: float | None = None
        geography_source = "unavailable"
        if destination_country:
            if destination_country.casefold() in self._high_risk_countries():
                geographic_signal = 100.0
                geography_source = "tenant-configured high-risk destination"
            elif (
                home_country
                and destination_country.casefold() != home_country.casefold()
            ):
                geographic_signal = 60.0
                geography_source = "cross-border transaction context"
            elif home_country:
                geographic_signal = 20.0
                geography_source = "destination matches customer residence"

        transaction_scores: list[float] = []
        if latest_anomaly is not None:
            transaction_scores.append(float(latest_anomaly.risk_score))
        if latest_analysis is not None:
            transaction_scores.append(float(latest_analysis.risk_score))
        transaction_signal = max(transaction_scores) if transaction_scores else None

        signals: dict[str, float | None] = {
            "alert_severity": PRIORITY_SCORE_BY_ALERT_LEVEL[case.priority],
            "customer_risk": float(profile.risk_score) if profile is not None else None,
            "transaction_risk": transaction_signal,
            "transaction_amount": amount_signal,
            "previous_history": history_score,
            "geographic_risk": geographic_signal,
        }
        score = calculate_priority_score(signals)

        reasons = [
            "Case alert severity is "
            f"{case.priority.value} (baseline signal "
            f"{signals['alert_severity']:.0f}/100)."
        ]
        if profile is not None:
            risk_level = self._enum_value(profile.risk_level) or "UNKNOWN"
            reasons.append(
                f"Customer risk profile is {risk_level} with score "
                f"{profile.risk_score}/100."
            )
        else:
            reasons.append(
                "No customer risk profile was available; this signal was omitted "
                "from the weighted score."
            )
        if transaction_signal is not None:
            reasons.append(
                "Latest available transaction-risk signal is "
                f"{transaction_signal:.2f}/100."
            )
        else:
            reasons.append(
                "No transaction-risk score was available; this signal was "
                "omitted from the weighted score."
            )
        if amount_ratio is not None and latest_transaction is not None:
            reasons.append(
                f"The latest observed {latest_transaction.currency} transaction "
                f"amount is {amount_ratio:.2f} times the same-currency "
                "historical median."
            )
        else:
            reasons.append(
                "A same-currency amount baseline was unavailable, so transaction "
                "amount did not increase or decrease the score."
            )
        if prior_cases:
            reasons.append(
                f"Customer history includes {len(prior_cases)} prior case(s), "
                f"of which {unresolved_count} are unresolved in the latest "
                "100-case window."
            )
        else:
            reasons.append(
                "No prior customer case history was available; this signal was "
                "omitted from the weighted score."
            )
        if geographic_signal is not None:
            reasons.append(
                f"Geography signal: {geography_source} ({geographic_signal:.0f}/100)."
            )
        else:
            reasons.append(
                "No destination-country signal was available; no country risk "
                "was inferred."
            )
        reasons.append(
            "This is an explainable prioritization aid; a qualified compliance "
            "professional must make the review decision."
        )

        snapshot: dict[str, Any] = {
            "algorithm_version": ALGORITHM_VERSION,
            "case_id": str(case.id),
            "case_type": self._enum_value(case.case_type),
            "case_priority": self._enum_value(case.priority),
            "case_status": self._enum_value(case.status),
            "customer_id": str(customer.id),
            "customer_residence": home_country or None,
            "customer_risk_score": profile.risk_score if profile is not None else None,
            "customer_risk_level": (
                self._enum_value(profile.risk_level) if profile is not None else None
            ),
            "latest_anomaly_id": (
                str(latest_anomaly.id) if latest_anomaly is not None else None
            ),
            "latest_anomaly_score": (
                str(latest_anomaly.risk_score) if latest_anomaly is not None else None
            ),
            "latest_transaction_risk_analysis_id": (
                str(latest_analysis.id) if latest_analysis is not None else None
            ),
            "latest_transaction_risk_score": (
                latest_analysis.risk_score if latest_analysis is not None else None
            ),
            "latest_transaction_id": (
                str(latest_transaction.transaction_id)
                if latest_transaction is not None
                else None
            ),
            "latest_transaction_amount": (
                str(latest_transaction.amount)
                if latest_transaction is not None
                else None
            ),
            "latest_transaction_currency": (
                latest_transaction.currency if latest_transaction is not None else None
            ),
            "transaction_amount_ratio_vs_median": amount_ratio,
            "latest_destination_country": destination_country or None,
            "prior_case_count_sampled": len(prior_cases),
            "prior_unresolved_case_count_sampled": unresolved_count,
            "signals": signals,
            "weights": PRIORITY_WEIGHTS,
        }
        return snapshot, score, " ".join(reasons)

    def prioritize_case(self, case_id: UUID) -> CasePriority:
        case = self._get_case(case_id)
        snapshot, score, reason = self._snapshot_and_score(case)
        latest = (
            self.db.query(CasePriority)
            .filter(
                CasePriority.tenant_id == self.tenant_id,
                CasePriority.case_id == case_id,
            )
            .order_by(CasePriority.created_at.desc())
            .first()
        )
        # Reads can safely refresh the priority after a source-risk change; do
        # not create duplicate history rows when the evidence has not changed.
        if latest is not None and latest.risk_snapshot == snapshot:
            return latest

        priority = CasePriority(
            tenant_id=self.tenant_id,
            case_id=case.id,
            priority_level=priority_level_for_score(score),
            priority_score=Decimal(str(score)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            ),
            reason=reason,
            risk_snapshot=snapshot,
        )
        self.db.add(priority)
        self.db.commit()
        self.db.refresh(priority)
        return priority

    def list_open_case_priorities(self, *, limit: int = 100) -> list[CasePriority]:
        cases = (
            self.db.query(ComplianceCase)
            .filter(
                ComplianceCase.tenant_id == self.tenant_id,
                ComplianceCase.status.in_(
                    {
                        ComplianceCaseStatus.OPEN,
                        ComplianceCaseStatus.ASSIGNED,
                        ComplianceCaseStatus.UNDER_REVIEW,
                        ComplianceCaseStatus.ESCALATED,
                    }
                ),
            )
            .order_by(ComplianceCase.created_at.desc())
            .limit(limit)
            .all()
        )
        priorities = [self.prioritize_case(case.id) for case in cases]
        return sorted(
            priorities,
            key=lambda item: float(item.priority_score),
            reverse=True,
        )

    def get_history(self, case_id: UUID) -> list[CasePriority]:
        self._get_case(case_id)
        return (
            self.db.query(CasePriority)
            .filter(
                CasePriority.tenant_id == self.tenant_id,
                CasePriority.case_id == case_id,
            )
            .order_by(CasePriority.created_at.desc())
            .all()
        )
