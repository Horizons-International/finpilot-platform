"""Endpoints for source-grounded AI compliance risk recommendations and history."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.responses import APIResponse
from app.core.security import require_roles
from app.schemas.ai_risk_recommendation import (
    AIRiskRecommendationGenerateRequest,
    AIRiskRecommendationHistoryResponse,
    AIRiskRecommendationResponse,
)
from app.services.ai_risk_recommendation_service import AIRiskRecommendationService
from app.utils.enums import UserRole

router = APIRouter(
    prefix="/api/v1/ai-risk-recommendations",
    tags=["AI Risk Recommendations"],
)

_GENERATE_ROLES = (
    UserRole.ADMINISTRATOR,
    UserRole.ORGANIZATION_ADMIN,
    UserRole.COMPLIANCE_MANAGER,
    UserRole.COMPLIANCE_OFFICER,
    UserRole.REVIEWER,
    UserRole.ANALYST,
)
_VIEW_ROLES = (*_GENERATE_ROLES, UserRole.VIEWER)


def _service(db: Session, current_user: dict[str, Any]) -> AIRiskRecommendationService:
    return AIRiskRecommendationService(db, tenant_id=UUID(current_user["tenant_id"]))


@router.post(
    "",
    response_model=APIResponse[AIRiskRecommendationResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Generate a compliance risk recommendation",
    description=(
        "Combines stored customer risk, transaction analysis, AML alerts, "
        "verification outcomes, previous compliance cases, and document analysis. "
        "The result is decision support and must be reviewed by a qualified person."
    ),
)
def generate_ai_risk_recommendation(
    payload: AIRiskRecommendationGenerateRequest,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(*_GENERATE_ROLES, resource_type="ai_risk_recommendation")
    ),
) -> APIResponse[AIRiskRecommendationResponse]:
    result = _service(db, current_user).generate(
        payload,
        user_id=UUID(current_user["sub"]),
    )
    return APIResponse(
        success=True,
        message="AI risk recommendation generated successfully.",
        data=AIRiskRecommendationResponse.model_validate(result),
    )


@router.get(
    "",
    response_model=APIResponse[AIRiskRecommendationHistoryResponse],
    summary="List AI risk recommendation history",
)
def list_ai_risk_recommendations(
    customer_id: UUID | None = Query(default=None),
    compliance_case_id: UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(*_VIEW_ROLES, resource_type="ai_risk_recommendation")
    ),
) -> APIResponse[AIRiskRecommendationHistoryResponse]:
    service = _service(db, current_user)
    items = service.list_history(
        customer_id=customer_id,
        compliance_case_id=compliance_case_id,
        limit=limit,
    )
    data = AIRiskRecommendationHistoryResponse(
        items=[AIRiskRecommendationResponse.model_validate(item) for item in items],
        total=service.repository.count_history(
            customer_id=customer_id,
            compliance_case_id=compliance_case_id,
        ),
    )
    return APIResponse(
        success=True,
        message="AI risk recommendation history retrieved successfully.",
        data=data,
    )


@router.get(
    "/{recommendation_id}",
    response_model=APIResponse[AIRiskRecommendationResponse],
    summary="Get a stored AI risk recommendation",
)
def get_ai_risk_recommendation(
    recommendation_id: UUID,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(*_VIEW_ROLES, resource_type="ai_risk_recommendation")
    ),
) -> APIResponse[AIRiskRecommendationResponse]:
    result = _service(db, current_user).get_recommendation(recommendation_id)
    return APIResponse(
        success=True,
        message="AI risk recommendation retrieved successfully.",
        data=AIRiskRecommendationResponse.model_validate(result),
    )
