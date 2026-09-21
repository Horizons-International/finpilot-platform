from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status

from app.core.dependencies import get_risk_scoring_service
from app.core.responses import APIResponse
from app.core.security import require_roles
from app.schemas.risk_scoring import (
    AppliedRiskRuleResponse,
    RiskScoringRequest,
    RiskScoringResponse,
)
from app.services.risk_scoring_service import RiskScoringService
from app.utils.enums import UserRole

router = APIRouter(
    prefix="/api/v1/customers",
    tags=["Risk Scoring"],
)


@router.post(
    "/{customer_id}/risk-score",
    response_model=APIResponse[RiskScoringResponse],
    status_code=status.HTTP_200_OK,
    summary="Calculate customer risk score",
    description=(
        "Calculate a customer's risk score using configured risk-scoring "
        "rules and store the resulting risk profile."
    ),
)
def calculate_customer_risk_score(
    customer_id: UUID,
    payload: RiskScoringRequest,
    request: Request,
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            resource_type="risk scoring",
        )
    ),
    service: RiskScoringService = Depends(get_risk_scoring_service),
) -> APIResponse[RiskScoringResponse]:
    profile = service.calculate_and_store(
        customer_id=customer_id,
        factors=payload.factors,
        risk_category=payload.risk_category,
        assessment_source=payload.assessment_source,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    applied_rules_data = []

    if profile.calculation_details:
        applied_rules_data = profile.calculation_details.get(
            "applied_rules",
            [],
        )

    applied_rules = [
        AppliedRiskRuleResponse.model_validate(rule) for rule in applied_rules_data
    ]

    return APIResponse(
        success=True,
        message="Customer risk score calculated successfully.",
        data=RiskScoringResponse(
            id=profile.id,
            customer_id=profile.customer_id,
            risk_score=profile.risk_score,
            risk_level=profile.risk_level,
            risk_category=profile.risk_category,
            assessment_source=profile.assessment_source,
            applied_rules=applied_rules,
        ),
    )
