from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.responses import APIResponse
from app.core.security import require_roles
from app.schemas.ai_model_metrics import (
    AIModelFeedbackCreate,
    AIModelFeedbackResponse,
    AIModelMetricResponse,
    AIModelMetricsSummaryResponse,
)
from app.services.ai_model_metrics_service import AIModelMetricsService
from app.utils.enums import UserRole

router = APIRouter(prefix="/api/v1/ai-model-metrics", tags=["AI Model Monitoring"])


@router.get(
    "/summary",
    response_model=APIResponse[AIModelMetricsSummaryResponse],
    summary="Get aggregate AI model performance",
)
def get_ai_model_metrics_summary(
    current_user: dict[str, Any] = Depends(require_roles(UserRole.ADMINISTRATOR)),
    db: Session = Depends(get_db),
) -> APIResponse[AIModelMetricsSummaryResponse]:
    service = AIModelMetricsService(db, tenant_id=UUID(current_user["tenant_id"]))
    return APIResponse(
        success=True,
        message="AI model performance summary retrieved successfully.",
        data=service.get_summary(),
    )


@router.get(
    "",
    response_model=APIResponse[list[AIModelMetricResponse]],
    summary="List AI model performance metrics",
)
def list_ai_model_metrics(
    model_name: str | None = Query(default=None, max_length=200),
    model_version: str | None = Query(default=None, max_length=100),
    current_user: dict[str, Any] = Depends(require_roles(UserRole.ADMINISTRATOR)),
    db: Session = Depends(get_db),
) -> APIResponse[list[AIModelMetricResponse]]:
    service = AIModelMetricsService(db, tenant_id=UUID(current_user["tenant_id"]))
    metrics = service.list_metrics(model_name=model_name, model_version=model_version)
    return APIResponse(
        success=True,
        message="AI model performance metrics retrieved successfully.",
        data=metrics,
    )


@router.post(
    "/interactions/{interaction_id}/feedback",
    response_model=APIResponse[AIModelFeedbackResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Submit feedback on an AI response",
    description=(
        "Stores user feedback and optional user-reported accuracy for an "
        "AI interaction. Users can only submit feedback on their own interaction."
    ),
)
def submit_ai_model_feedback(
    interaction_id: UUID,
    payload: AIModelFeedbackCreate,
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_MANAGER,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
        )
    ),
    db: Session = Depends(get_db),
) -> APIResponse[AIModelFeedbackResponse]:
    service = AIModelMetricsService(db, tenant_id=UUID(current_user["tenant_id"]))
    feedback = service.submit_feedback(
        interaction_id,
        user_id=UUID(current_user["sub"]),
        rating=payload.rating,
        is_accurate=payload.is_accurate,
        comment=payload.comment,
    )
    return APIResponse(
        success=True,
        message="AI response feedback recorded successfully.",
        data=AIModelFeedbackResponse.model_validate(feedback),
    )
