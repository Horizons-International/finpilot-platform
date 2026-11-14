"""Async customer risk-scoring endpoint."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.async_security import require_async_roles
from app.core.database import get_async_db
from app.core.responses import APIResponse
from app.schemas.risk_scoring import (
    AppliedRiskRuleResponse,
    RiskScoringRequest,
    RiskScoringResponse,
)
from app.services.async_risk_scoring_service import AsyncRiskScoringService
from app.utils.enums import UserRole

router = APIRouter(prefix="/api/v1/customers", tags=["Risk Scoring"])


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
async def calculate_customer_risk_score(
    customer_id: UUID,
    payload: RiskScoringRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            resource_type="risk_score",
        )
    ),
) -> APIResponse[RiskScoringResponse]:
    profile = await AsyncRiskScoringService(
        db, UUID(current_user["tenant_id"])
    ).calculate_and_store(
        customer_id=customer_id,
        factors=payload.factors,
        risk_category=payload.risk_category,
        assessment_source=payload.assessment_source,
        user_id=UUID(current_user["sub"]),
        email=str(current_user.get("email") or ""),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    applied_rules_data: list[dict[str, Any]] = []
    if profile.calculation_details:
        raw_rules = profile.calculation_details.get("applied_rules", [])
        if isinstance(raw_rules, list):
            applied_rules_data = [item for item in raw_rules if isinstance(item, dict)]
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
            applied_rules=[
                AppliedRiskRuleResponse.model_validate(item)
                for item in applied_rules_data
            ],
        ),
    )
