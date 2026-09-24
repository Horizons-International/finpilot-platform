from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.utils.enums import (
    AMLRuleSeverity,
    AMLRuleStatus,
    AMLRuleType,
)


class AMLRuleCreate(BaseModel):
    name: str = Field(
        min_length=1,
        max_length=200,
    )

    description: str | None = Field(
        default=None,
        max_length=2000,
    )

    rule_type: AMLRuleType

    condition: dict[str, Any] = Field(
        min_length=1,
    )

    severity: AMLRuleSeverity

    status: AMLRuleStatus = AMLRuleStatus.ACTIVE


class AMLRuleStatusUpdate(BaseModel):
    status: AMLRuleStatus


class AMLRuleResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: UUID
    name: str
    description: str | None
    rule_type: AMLRuleType
    condition: dict[str, Any]
    severity: AMLRuleSeverity
    status: AMLRuleStatus


class AMLRuleEvaluationRequest(BaseModel):
    rule_type: AMLRuleType

    data: dict[str, Any] = Field(
        min_length=1,
    )


class AMLRuleEvaluationItemResponse(BaseModel):
    rule_id: UUID
    rule_name: str
    rule_type: AMLRuleType
    severity: AMLRuleSeverity
    matched: bool


class AMLRuleMatchResponse(BaseModel):
    rule_id: UUID
    rule_name: str
    rule_type: AMLRuleType
    severity: AMLRuleSeverity
    matched: bool
    alert_required: bool


class AMLRuleEvaluationResponse(BaseModel):
    rule_type: AMLRuleType
    evaluated_rule_count: int
    matched_rule_count: int
    evaluations: list[AMLRuleEvaluationItemResponse]
    matches: list[AMLRuleMatchResponse]
