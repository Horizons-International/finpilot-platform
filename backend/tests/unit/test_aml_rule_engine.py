from uuid import uuid4

import pytest

from app.models.aml_rule import AMLRule
from app.services.aml_rule_engine import AMLRuleEngine
from app.utils.enums import (
    AMLRuleSeverity,
    AMLRuleStatus,
    AMLRuleType,
)


def create_rule(
    *,
    condition: dict,
    name: str = "Test AML Rule",
) -> AMLRule:
    return AMLRule(
        id=uuid4(),
        name=name,
        description="Test rule",
        rule_type=AMLRuleType.CUSTOMER_RISK,
        condition=condition,
        severity=AMLRuleSeverity.HIGH,
        status=AMLRuleStatus.ACTIVE,
    )


def test_high_risk_country_condition_matches():
    rule = create_rule(
        condition={
            "field": "country",
            "operator": "=",
            "value": "HIGH_RISK",
        }
    )

    engine = AMLRuleEngine()

    result = engine.evaluate(
        rule_type=AMLRuleType.CUSTOMER_RISK,
        rules=[rule],
        data={
            "country": "HIGH_RISK",
        },
    )

    assert result.evaluated_rule_count == 1
    assert result.matched_rule_count == 1

    match = result.matches[0]

    assert match.rule_id == rule.id
    assert match.rule_name == rule.name
    assert match.severity == AMLRuleSeverity.HIGH
    assert match.matched is True
    assert match.alert_required is True


def test_high_risk_country_condition_does_not_match():
    rule = create_rule(
        condition={
            "field": "country",
            "operator": "=",
            "value": "HIGH_RISK",
        }
    )

    engine = AMLRuleEngine()

    result = engine.evaluate(
        rule_type=AMLRuleType.CUSTOMER_RISK,
        rules=[rule],
        data={
            "country": "LOW_RISK",
        },
    )

    assert result.evaluated_rule_count == 1
    assert result.matched_rule_count == 0
    assert result.matches == []


def test_numeric_transaction_condition_matches():
    rule = create_rule(
        condition={
            "field": "transaction_amount",
            "operator": ">",
            "value": 10000,
        },
    )

    rule.rule_type = AMLRuleType.TRANSACTION

    engine = AMLRuleEngine()

    result = engine.evaluate(
        rule_type=AMLRuleType.TRANSACTION,
        rules=[rule],
        data={
            "transaction_amount": 15000,
        },
    )

    assert result.matched_rule_count == 1


def test_numeric_type_mismatch_does_not_match():
    rule = create_rule(
        condition={
            "field": "transaction_amount",
            "operator": ">",
            "value": 10000,
        },
    )

    rule.rule_type = AMLRuleType.TRANSACTION

    engine = AMLRuleEngine()

    result = engine.evaluate(
        rule_type=AMLRuleType.TRANSACTION,
        rules=[rule],
        data={
            "transaction_amount": "fifteen thousand",
        },
    )

    assert result.matched_rule_count == 0


def test_in_operator_matches():
    rule = create_rule(
        condition={
            "field": "country",
            "operator": "IN",
            "value": [
                "COUNTRY_A",
                "COUNTRY_B",
            ],
        },
    )

    engine = AMLRuleEngine()

    result = engine.evaluate(
        rule_type=AMLRuleType.CUSTOMER_RISK,
        rules=[rule],
        data={
            "country": "COUNTRY_A",
        },
    )

    assert result.matched_rule_count == 1


def test_in_operator_does_not_match():
    rule = create_rule(
        condition={
            "field": "country",
            "operator": "IN",
            "value": [
                "COUNTRY_A",
                "COUNTRY_B",
            ],
        },
    )

    engine = AMLRuleEngine()

    result = engine.evaluate(
        rule_type=AMLRuleType.CUSTOMER_RISK,
        rules=[rule],
        data={
            "country": "COUNTRY_C",
        },
    )

    assert result.matched_rule_count == 0


def test_all_condition_requires_every_condition():
    rule = create_rule(
        condition={
            "all": [
                {
                    "field": "country",
                    "operator": "=",
                    "value": "HIGH_RISK",
                },
                {
                    "field": "risk_level",
                    "operator": "=",
                    "value": "HIGH",
                },
            ],
        },
    )

    engine = AMLRuleEngine()

    result = engine.evaluate(
        rule_type=AMLRuleType.CUSTOMER_RISK,
        rules=[rule],
        data={
            "country": "HIGH_RISK",
            "risk_level": "HIGH",
        },
    )

    assert result.matched_rule_count == 1


def test_all_condition_does_not_match_when_one_condition_fails():
    rule = create_rule(
        condition={
            "all": [
                {
                    "field": "country",
                    "operator": "=",
                    "value": "HIGH_RISK",
                },
                {
                    "field": "risk_level",
                    "operator": "=",
                    "value": "HIGH",
                },
            ],
        },
    )

    engine = AMLRuleEngine()

    result = engine.evaluate(
        rule_type=AMLRuleType.CUSTOMER_RISK,
        rules=[rule],
        data={
            "country": "HIGH_RISK",
            "risk_level": "LOW",
        },
    )

    assert result.matched_rule_count == 0


def test_any_condition_matches_when_one_condition_matches():
    rule = create_rule(
        condition={
            "any": [
                {
                    "field": "country",
                    "operator": "=",
                    "value": "HIGH_RISK",
                },
                {
                    "field": "risk_level",
                    "operator": "=",
                    "value": "CRITICAL",
                },
            ],
        },
    )

    engine = AMLRuleEngine()

    result = engine.evaluate(
        rule_type=AMLRuleType.CUSTOMER_RISK,
        rules=[rule],
        data={
            "country": "LOW_RISK",
            "risk_level": "CRITICAL",
        },
    )

    assert result.matched_rule_count == 1


def test_nested_field_condition_matches():
    rule = create_rule(
        condition={
            "field": "customer.risk_level",
            "operator": "=",
            "value": "HIGH",
        },
    )

    engine = AMLRuleEngine()

    result = engine.evaluate(
        rule_type=AMLRuleType.CUSTOMER_RISK,
        rules=[rule],
        data={
            "customer": {
                "risk_level": "HIGH",
            },
        },
    )

    assert result.matched_rule_count == 1


def test_missing_field_does_not_match():
    rule = create_rule(
        condition={
            "field": "country",
            "operator": "=",
            "value": "HIGH_RISK",
        },
    )

    engine = AMLRuleEngine()

    result = engine.evaluate(
        rule_type=AMLRuleType.CUSTOMER_RISK,
        rules=[rule],
        data={},
    )

    assert result.matched_rule_count == 0


def test_invalid_operator_is_rejected():
    with pytest.raises(
        ValueError,
        match="Unsupported AML rule operator",
    ):
        AMLRuleEngine.validate_condition(
            {
                "field": "country",
                "operator": "CONTAINS",
                "value": "HIGH_RISK",
            },
        )


def test_missing_field_is_rejected():
    with pytest.raises(
        ValueError,
        match="condition field is required",
    ):
        AMLRuleEngine.validate_condition(
            {
                "operator": "=",
                "value": "HIGH_RISK",
            },
        )


def test_missing_value_is_rejected():
    with pytest.raises(
        ValueError,
        match="condition value is required",
    ):
        AMLRuleEngine.validate_condition(
            {
                "field": "country",
                "operator": "=",
            },
        )


def test_empty_all_is_rejected():
    with pytest.raises(
        ValueError,
        match="all",
    ):
        AMLRuleEngine.validate_condition(
            {
                "all": [],
            },
        )


def test_empty_any_is_rejected():
    with pytest.raises(
        ValueError,
        match="any",
    ):
        AMLRuleEngine.validate_condition(
            {
                "any": [],
            },
        )


def test_multiple_condition_modes_are_rejected():
    with pytest.raises(
        ValueError,
        match="either",
    ):
        AMLRuleEngine.validate_condition(
            {
                "field": "country",
                "operator": "=",
                "value": "HIGH_RISK",
                "all": [],
            },
        )
