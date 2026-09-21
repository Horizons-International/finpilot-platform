import pytest

from app.models.risk_score_threshold import RiskScoreThreshold
from app.models.risk_scoring_rule import RiskScoringRule
from app.services.risk_scoring_engine import RiskScoringEngine
from app.utils.enums import CustomerRiskLevel, RiskRuleOperator


@pytest.fixture
def engine():
    return RiskScoringEngine()


@pytest.fixture
def thresholds():
    return [
        RiskScoreThreshold(
            risk_level=CustomerRiskLevel.LOW,
            min_score=0,
            max_score=30,
            is_active=True,
        ),
        RiskScoreThreshold(
            risk_level=CustomerRiskLevel.MEDIUM,
            min_score=31,
            max_score=70,
            is_active=True,
        ),
        RiskScoreThreshold(
            risk_level=CustomerRiskLevel.HIGH,
            min_score=71,
            max_score=100,
            is_active=True,
        ),
    ]


def make_rule(
    *,
    factor_key: str,
    operator: RiskRuleOperator,
    expected_value,
    score_points: int,
):
    return RiskScoringRule(
        factor_key=factor_key,
        operator=operator,
        expected_value=expected_value,
        score_points=score_points,
        is_active=True,
    )


def test_low_risk_score_is_assigned_low_level(
    engine,
    thresholds,
):
    rules = [
        make_rule(
            factor_key="country",
            operator=RiskRuleOperator.EQUALS,
            expected_value="SD",
            score_points=20,
        ),
    ]

    result = engine.calculate(
        factors={
            "country": "SD",
        },
        rules=rules,
        thresholds=thresholds,
    )

    assert result.score == 20
    assert result.risk_level == CustomerRiskLevel.LOW
    assert len(result.applied_rules) == 1
    assert result.applied_rules[0].factor_key == "country"
    assert result.applied_rules[0].score_points == 20


def test_medium_risk_score_is_assigned_medium_level(
    engine,
    thresholds,
):
    rules = [
        make_rule(
            factor_key="country",
            operator=RiskRuleOperator.EQUALS,
            expected_value="SD",
            score_points=30,
        ),
        make_rule(
            factor_key="verification_status",
            operator=RiskRuleOperator.EQUALS,
            expected_value="PENDING",
            score_points=30,
        ),
    ]

    result = engine.calculate(
        factors={
            "country": "SD",
            "verification_status": "PENDING",
        },
        rules=rules,
        thresholds=thresholds,
    )

    assert result.score == 60
    assert result.risk_level == CustomerRiskLevel.MEDIUM
    assert len(result.applied_rules) == 2


def test_high_risk_score_is_assigned_high_level(
    engine,
    thresholds,
):
    rules = [
        make_rule(
            factor_key="country",
            operator=RiskRuleOperator.EQUALS,
            expected_value="HIGH_RISK",
            score_points=40,
        ),
        make_rule(
            factor_key="verification_status",
            operator=RiskRuleOperator.EQUALS,
            expected_value="REJECTED",
            score_points=40,
        ),
    ]

    result = engine.calculate(
        factors={
            "country": "HIGH_RISK",
            "verification_status": "REJECTED",
        },
        rules=rules,
        thresholds=thresholds,
    )

    assert result.score == 80
    assert result.risk_level == CustomerRiskLevel.HIGH
    assert len(result.applied_rules) == 2


@pytest.mark.parametrize(
    ("score", "expected_level"),
    [
        (0, CustomerRiskLevel.LOW),
        (30, CustomerRiskLevel.LOW),
        (31, CustomerRiskLevel.MEDIUM),
        (70, CustomerRiskLevel.MEDIUM),
        (71, CustomerRiskLevel.HIGH),
        (100, CustomerRiskLevel.HIGH),
    ],
)
def test_risk_threshold_boundaries(
    engine,
    thresholds,
    score,
    expected_level,
):
    rules = [
        make_rule(
            factor_key="score_factor",
            operator=RiskRuleOperator.EQUALS,
            expected_value="MATCH",
            score_points=score,
        ),
    ]

    result = engine.calculate(
        factors={
            "score_factor": "MATCH",
        },
        rules=rules,
        thresholds=thresholds,
    )

    assert result.score == score
    assert result.risk_level == expected_level


def test_non_matching_rule_is_not_applied(
    engine,
    thresholds,
):
    rules = [
        make_rule(
            factor_key="country",
            operator=RiskRuleOperator.EQUALS,
            expected_value="US",
            score_points=50,
        ),
    ]

    result = engine.calculate(
        factors={
            "country": "SD",
        },
        rules=rules,
        thresholds=thresholds,
    )

    assert result.score == 0
    assert result.risk_level == CustomerRiskLevel.LOW
    assert result.applied_rules == []


def test_multiple_matching_rules_are_added(
    engine,
    thresholds,
):
    rules = [
        make_rule(
            factor_key="country",
            operator=RiskRuleOperator.EQUALS,
            expected_value="SD",
            score_points=20,
        ),
        make_rule(
            factor_key="customer_type",
            operator=RiskRuleOperator.EQUALS,
            expected_value="BUSINESS",
            score_points=25,
        ),
        make_rule(
            factor_key="verification_status",
            operator=RiskRuleOperator.EQUALS,
            expected_value="PENDING",
            score_points=15,
        ),
    ]

    result = engine.calculate(
        factors={
            "country": "SD",
            "customer_type": "BUSINESS",
            "verification_status": "PENDING",
        },
        rules=rules,
        thresholds=thresholds,
    )

    assert result.score == 60
    assert result.risk_level == CustomerRiskLevel.MEDIUM
    assert len(result.applied_rules) == 3


def test_equals_operator(
    engine,
    thresholds,
):
    rules = [
        make_rule(
            factor_key="country",
            operator=RiskRuleOperator.EQUALS,
            expected_value="SD",
            score_points=20,
        ),
    ]

    result = engine.calculate(
        factors={"country": "SD"},
        rules=rules,
        thresholds=thresholds,
    )

    assert result.score == 20


def test_not_equals_operator(
    engine,
    thresholds,
):
    rules = [
        make_rule(
            factor_key="country",
            operator=RiskRuleOperator.NOT_EQUALS,
            expected_value="US",
            score_points=20,
        ),
    ]

    result = engine.calculate(
        factors={"country": "SD"},
        rules=rules,
        thresholds=thresholds,
    )

    assert result.score == 20


def test_in_operator(
    engine,
    thresholds,
):
    rules = [
        make_rule(
            factor_key="country",
            operator=RiskRuleOperator.IN,
            expected_value=["SD", "UG", "KE"],
            score_points=25,
        ),
    ]

    result = engine.calculate(
        factors={"country": "SD"},
        rules=rules,
        thresholds=thresholds,
    )

    assert result.score == 25


def test_in_operator_does_not_match_non_list_expected_value(
    engine,
    thresholds,
):
    rules = [
        make_rule(
            factor_key="country",
            operator=RiskRuleOperator.IN,
            expected_value="SD",
            score_points=25,
        ),
    ]

    result = engine.calculate(
        factors={"country": "SD"},
        rules=rules,
        thresholds=thresholds,
    )

    assert result.score == 0


def test_not_in_operator(
    engine,
    thresholds,
):
    rules = [
        make_rule(
            factor_key="country",
            operator=RiskRuleOperator.NOT_IN,
            expected_value=["US", "GB"],
            score_points=25,
        ),
    ]

    result = engine.calculate(
        factors={"country": "SD"},
        rules=rules,
        thresholds=thresholds,
    )

    assert result.score == 25


def test_greater_than_operator(
    engine,
    thresholds,
):
    rules = [
        make_rule(
            factor_key="previous_cases",
            operator=RiskRuleOperator.GREATER_THAN,
            expected_value=2,
            score_points=30,
        ),
    ]

    result = engine.calculate(
        factors={"previous_cases": 3},
        rules=rules,
        thresholds=thresholds,
    )

    assert result.score == 30


def test_greater_than_or_equal_operator(
    engine,
    thresholds,
):
    rules = [
        make_rule(
            factor_key="previous_cases",
            operator=RiskRuleOperator.GREATER_THAN_OR_EQUAL,
            expected_value=2,
            score_points=30,
        ),
    ]

    result = engine.calculate(
        factors={"previous_cases": 2},
        rules=rules,
        thresholds=thresholds,
    )

    assert result.score == 30


def test_less_than_operator(
    engine,
    thresholds,
):
    rules = [
        make_rule(
            factor_key="transaction_count",
            operator=RiskRuleOperator.LESS_THAN,
            expected_value=10,
            score_points=15,
        ),
    ]

    result = engine.calculate(
        factors={"transaction_count": 5},
        rules=rules,
        thresholds=thresholds,
    )

    assert result.score == 15


def test_less_than_or_equal_operator(
    engine,
    thresholds,
):
    rules = [
        make_rule(
            factor_key="transaction_count",
            operator=RiskRuleOperator.LESS_THAN_OR_EQUAL,
            expected_value=10,
            score_points=15,
        ),
    ]

    result = engine.calculate(
        factors={"transaction_count": 10},
        rules=rules,
        thresholds=thresholds,
    )

    assert result.score == 15


def test_exists_operator(
    engine,
    thresholds,
):
    rules = [
        make_rule(
            factor_key="previous_compliance_case",
            operator=RiskRuleOperator.EXISTS,
            expected_value=None,
            score_points=25,
        ),
    ]

    result = engine.calculate(
        factors={
            "previous_compliance_case": {
                "case_id": "case-1",
            },
        },
        rules=rules,
        thresholds=thresholds,
    )

    assert result.score == 25


def test_exists_operator_does_not_match_missing_factor(
    engine,
    thresholds,
):
    rules = [
        make_rule(
            factor_key="previous_compliance_case",
            operator=RiskRuleOperator.EXISTS,
            expected_value=None,
            score_points=25,
        ),
    ]

    result = engine.calculate(
        factors={},
        rules=rules,
        thresholds=thresholds,
    )

    assert result.score == 0


def test_not_exists_operator(
    engine,
    thresholds,
):
    rules = [
        make_rule(
            factor_key="previous_compliance_case",
            operator=RiskRuleOperator.NOT_EXISTS,
            expected_value=None,
            score_points=25,
        ),
    ]

    result = engine.calculate(
        factors={},
        rules=rules,
        thresholds=thresholds,
    )

    assert result.score == 25


def test_missing_factor_does_not_match_normal_operator(
    engine,
    thresholds,
):
    rules = [
        make_rule(
            factor_key="country",
            operator=RiskRuleOperator.EQUALS,
            expected_value="SD",
            score_points=20,
        ),
    ]

    result = engine.calculate(
        factors={},
        rules=rules,
        thresholds=thresholds,
    )

    assert result.score == 0


def test_applied_rules_contain_rule_ids(
    engine,
    thresholds,
):
    rule = make_rule(
        factor_key="country",
        operator=RiskRuleOperator.EQUALS,
        expected_value="SD",
        score_points=20,
    )

    result = engine.calculate(
        factors={"country": "SD"},
        rules=[rule],
        thresholds=thresholds,
    )

    assert len(result.applied_rules) == 1
    assert result.applied_rules[0].rule_id == str(rule.id)


def test_missing_threshold_raises_value_error(
    engine,
):
    rules = [
        make_rule(
            factor_key="country",
            operator=RiskRuleOperator.EQUALS,
            expected_value="SD",
            score_points=20,
        ),
    ]

    with pytest.raises(
        ValueError,
        match="No risk level threshold is configured",
    ):
        engine.calculate(
            factors={"country": "SD"},
            rules=rules,
            thresholds=[],
        )


def test_type_mismatch_does_not_match_numeric_operator(
    engine,
    thresholds,
):
    rules = [
        make_rule(
            factor_key="previous_cases",
            operator=RiskRuleOperator.GREATER_THAN,
            expected_value=2,
            score_points=30,
        ),
    ]

    result = engine.calculate(
        factors={"previous_cases": "three"},
        rules=rules,
        thresholds=thresholds,
    )

    assert result.score == 0
