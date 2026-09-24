from dataclasses import dataclass
from typing import Any

from app.models.risk_score_threshold import RiskScoreThreshold
from app.models.risk_scoring_rule import RiskScoringRule
from app.utils.enums import CustomerRiskLevel, RiskRuleOperator


@dataclass(frozen=True)
class AppliedRiskRule:
    rule_id: str
    factor_key: str
    score_points: int


@dataclass(frozen=True)
class RiskScoreResult:
    score: int
    risk_level: CustomerRiskLevel
    applied_rules: list[AppliedRiskRule]


class RiskScoringEngine:
    def calculate(
        self,
        *,
        factors: dict[str, Any],
        rules: list[RiskScoringRule],
        thresholds: list[RiskScoreThreshold],
    ) -> RiskScoreResult:
        score = 0
        applied_rules: list[AppliedRiskRule] = []

        for rule in rules:
            factor_value = factors.get(rule.factor_key)

            if not self._matches(
                factor_value=factor_value,
                operator=rule.operator,
                expected_value=rule.expected_value,
            ):
                continue

            score += rule.score_points

            applied_rules.append(
                AppliedRiskRule(
                    rule_id=str(rule.id),
                    factor_key=rule.factor_key,
                    score_points=rule.score_points,
                )
            )

        risk_level = self._resolve_risk_level(
            score=score,
            thresholds=thresholds,
        )

        return RiskScoreResult(
            score=score,
            risk_level=risk_level,
            applied_rules=applied_rules,
        )

    def _matches(
        self,
        *,
        factor_value: Any,
        operator: RiskRuleOperator,
        expected_value: Any,
    ) -> bool:
        try:
            if operator == RiskRuleOperator.EQUALS:
                return bool(factor_value == expected_value)

            if operator == RiskRuleOperator.NOT_EQUALS:
                return bool(factor_value != expected_value)

            if operator == RiskRuleOperator.IN:
                if not isinstance(
                    expected_value,
                    (list, tuple, set),
                ):
                    return False

                return factor_value in expected_value

            if operator == RiskRuleOperator.NOT_IN:
                if not isinstance(
                    expected_value,
                    (list, tuple, set),
                ):
                    return False

                return factor_value not in expected_value

            if operator == RiskRuleOperator.GREATER_THAN:
                return bool(factor_value > expected_value)

            if operator == RiskRuleOperator.GREATER_THAN_OR_EQUAL:
                return bool(factor_value >= expected_value)

            if operator == RiskRuleOperator.LESS_THAN:
                return bool(factor_value < expected_value)

            if operator == RiskRuleOperator.LESS_THAN_OR_EQUAL:
                return bool(factor_value <= expected_value)

            if operator == RiskRuleOperator.EXISTS:
                return factor_value is not None

            if operator == RiskRuleOperator.NOT_EXISTS:
                return factor_value is None

            return False

        except TypeError:
            return False

    @staticmethod
    def _resolve_risk_level(
        *,
        score: int,
        thresholds: list[RiskScoreThreshold],
    ) -> CustomerRiskLevel:
        for threshold in thresholds:
            if threshold.min_score <= score <= threshold.max_score:
                return threshold.risk_level

        raise ValueError(f"No risk level threshold is configured for score {score}.")
