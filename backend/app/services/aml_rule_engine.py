from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.models.aml_rule import AMLRule
from app.utils.enums import (
    AMLRuleSeverity,
    AMLRuleType,
)

SUPPORTED_OPERATORS = {
    "=",
    "!=",
    ">",
    ">=",
    "<",
    "<=",
    "IN",
    "NOT_IN",
    "EXISTS",
    "NOT_EXISTS",
}


@dataclass(frozen=True)
class AMLRuleEvaluation:
    rule_id: UUID
    rule_name: str
    rule_type: AMLRuleType
    severity: AMLRuleSeverity
    matched: bool


@dataclass(frozen=True)
class AMLRuleMatch:
    rule_id: UUID
    rule_name: str
    rule_type: AMLRuleType
    severity: AMLRuleSeverity
    matched: bool
    alert_required: bool


@dataclass(frozen=True)
class AMLRuleEvaluationResult:
    rule_type: AMLRuleType
    evaluated_rule_count: int
    evaluations: list[AMLRuleEvaluation]
    matches: list[AMLRuleMatch]

    @property
    def matched_rule_count(self) -> int:
        return len(self.matches)


class AMLRuleEngine:
    def evaluate(
        self,
        *,
        rule_type: AMLRuleType,
        rules: list[AMLRule],
        data: dict[str, Any],
    ) -> AMLRuleEvaluationResult:
        evaluations: list[AMLRuleEvaluation] = []
        matches: list[AMLRuleMatch] = []

        for rule in rules:
            matched = self.evaluate_condition(
                condition=rule.condition,
                data=data,
            )

            evaluations.append(
                AMLRuleEvaluation(
                    rule_id=rule.id,
                    rule_name=rule.name,
                    rule_type=rule.rule_type,
                    severity=rule.severity,
                    matched=matched,
                )
            )

            if not matched:
                continue

            matches.append(
                AMLRuleMatch(
                    rule_id=rule.id,
                    rule_name=rule.name,
                    rule_type=rule.rule_type,
                    severity=rule.severity,
                    matched=True,
                    alert_required=True,
                )
            )

        return AMLRuleEvaluationResult(
            rule_type=rule_type,
            evaluated_rule_count=len(rules),
            evaluations=evaluations,
            matches=matches,
        )

    def evaluate_condition(
        self,
        *,
        condition: dict[str, Any],
        data: dict[str, Any],
    ) -> bool:
        self.validate_condition(condition)

        if "all" in condition:
            conditions = condition["all"]

            return all(
                self.evaluate_condition(
                    condition=subcondition,
                    data=data,
                )
                for subcondition in conditions
            )

        if "any" in condition:
            conditions = condition["any"]

            return any(
                self.evaluate_condition(
                    condition=subcondition,
                    data=data,
                )
                for subcondition in conditions
            )

        field = condition["field"]
        operator = condition["operator"]
        expected_value = condition.get("value")

        actual_exists, actual_value = self._get_field(
            data=data,
            field=field,
        )

        if operator == "EXISTS":
            return actual_exists and actual_value is not None

        if operator == "NOT_EXISTS":
            return not actual_exists or actual_value is None

        if not actual_exists:
            return False

        try:
            if operator == "=":
                return bool(actual_value == expected_value)

            if operator == "!=":
                return bool(actual_value != expected_value)

            if operator == ">":
                return bool(actual_value > expected_value)

            if operator == ">=":
                return bool(actual_value >= expected_value)

            if operator == "<":
                return bool(actual_value < expected_value)

            if operator == "<=":
                return bool(actual_value <= expected_value)

            if operator == "IN":
                if not isinstance(
                    expected_value,
                    list,
                ):
                    return False

                return actual_value in expected_value

            if operator == "NOT_IN":
                if not isinstance(
                    expected_value,
                    list,
                ):
                    return False

                return actual_value not in expected_value

        except TypeError:
            return False

        return False

    @staticmethod
    def validate_condition(
        condition: dict[str, Any],
    ) -> None:
        if not isinstance(condition, dict):
            raise ValueError("AML rule condition must be an object.")

        has_simple_condition = "field" in condition or "operator" in condition

        has_all = "all" in condition
        has_any = "any" in condition

        condition_modes = sum(
            [
                has_simple_condition,
                has_all,
                has_any,
            ]
        )

        if condition_modes != 1:
            raise ValueError(
                "AML rule condition must contain either "
                "'field'/'operator', 'all', or 'any'."
            )

        if has_simple_condition:
            field = condition.get("field")
            operator = condition.get("operator")

            if not isinstance(field, str) or not field:
                raise ValueError("AML rule condition field is required.")

            if operator not in SUPPORTED_OPERATORS:
                raise ValueError(f"Unsupported AML rule operator: {operator}.")

            if (
                operator
                not in {
                    "EXISTS",
                    "NOT_EXISTS",
                }
                and "value" not in condition
            ):
                raise ValueError("AML rule condition value is required.")

            return

        if has_all:
            conditions = condition["all"]

            if not isinstance(conditions, list) or not conditions:
                raise ValueError("'all' must contain at least one condition.")

            for subcondition in conditions:
                if not isinstance(
                    subcondition,
                    dict,
                ):
                    raise ValueError("Every AML condition in 'all' must be an object.")

                AMLRuleEngine.validate_condition(
                    subcondition,
                )

            return

        conditions = condition["any"]

        if not isinstance(conditions, list) or not conditions:
            raise ValueError("'any' must contain at least one condition.")

        for subcondition in conditions:
            if not isinstance(
                subcondition,
                dict,
            ):
                raise ValueError("Every AML condition in 'any' must be an object.")

            AMLRuleEngine.validate_condition(
                subcondition,
            )

    @staticmethod
    def _get_field(
        *,
        data: dict[str, Any],
        field: str,
    ) -> tuple[bool, Any]:
        current: Any = data

        for part in field.split("."):
            if not isinstance(
                current,
                dict,
            ):
                return False, None

            if part not in current:
                return False, None

            current = current[part]

        return True, current
