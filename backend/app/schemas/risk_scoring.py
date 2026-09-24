from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.utils.enums import CustomerRiskLevel, RiskRuleOperator


class RiskScoringRequest(BaseModel):
    factors: dict[str, Any] = Field(
        min_length=1,
    )

    risk_category: str = Field(
        min_length=1,
        max_length=100,
    )

    assessment_source: str = Field(
        min_length=1,
        max_length=100,
    )


class AppliedRiskRuleResponse(BaseModel):
    rule_id: UUID
    factor_key: str
    score_points: int


class RiskScoringResponse(BaseModel):
    id: UUID
    customer_id: UUID
    risk_score: int
    risk_level: CustomerRiskLevel
    risk_category: str
    assessment_source: str
    applied_rules: list[AppliedRiskRuleResponse]


class RiskScoringRuleCreate(BaseModel):
    factor_key: str = Field(
        min_length=1,
        max_length=100,
    )
    operator: RiskRuleOperator
    expected_value: Any | None = None
    score_points: int = Field(
        ge=0,
    )
    description: str | None = Field(
        default=None,
        max_length=1000,
    )
    priority: int = 0
    is_active: bool = True


class RiskScoringRuleStatusUpdate(BaseModel):
    is_active: bool


class RiskScoringRuleResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: UUID
    factor_key: str
    operator: RiskRuleOperator
    expected_value: Any | None
    score_points: int
    description: str | None
    priority: int
    is_active: bool


class RiskScoringRuleUpdate(BaseModel):
    factor_key: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )
    operator: RiskRuleOperator | None = None
    expected_value: Any | None = None
    score_points: int | None = Field(
        default=None,
        ge=0,
    )
    description: str | None = Field(
        default=None,
        max_length=1000,
    )
    priority: int | None = None
    is_active: bool | None = None
