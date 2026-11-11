from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.ai.exceptions import AIProviderError
from app.core.async_security import require_async_roles
from app.core.database import get_async_db
from app.core.dependencies import (
    get_ai_analytics_assistant_service,
    get_ai_compliance_service,
    get_regulatory_assistant_service,
)
from app.core.responses import APIResponse
from app.core.security import require_roles
from app.models.ai_interaction import AIInteraction
from app.schemas.ai_analytics_assistant import AIAnalyticsResponse
from app.schemas.ai_assistant import (
    AIComplianceRequest,
    AIComplianceResponse,
    AIInteractionResponse,
)
from app.schemas.ai_decision_explanation import (
    AIDecisionExplanationHistoryResponse,
    AIDecisionExplanationResponse,
)
from app.schemas.regulatory_assistant import (
    RegulatoryAssistantAnswerResponse,
    RegulatoryAssistantRequest,
    RegulatoryAssistantSearchResponse,
)
from app.services.ai_analytics_assistant_service import AIAnalyticsAssistantService
from app.services.ai_compliance_service import AIComplianceService
from app.services.ai_decision_explanation_recorder import (
    install_ai_decision_explanation_recorder,
)
from app.services.ai_decision_explanation_service import AIDecisionExplanationService
from app.services.async_service_bridge import run_sync_in_tenant
from app.services.regulatory_assistant_service import RegulatoryAssistantService
from app.utils.enums import UserRole
from app.utils.errors import bad_request, not_found, service_unavailable

router = APIRouter(prefix="/api/v1/ai-assistant", tags=["AI Assistant"])

REGULATORY_ASSISTANT_ROLES = (
    UserRole.ADMINISTRATOR,
    UserRole.COMPLIANCE_MANAGER,
    UserRole.COMPLIANCE_OFFICER,
    UserRole.REVIEWER,
    UserRole.AUDITOR,
)


# AI provider calls below intentionally remain synchronous: the configured OpenAI
# adapter uses the synchronous SDK and FastAPI dispatches these `def` handlers to
# its worker pool. Database-backed read endpoints use AsyncSession instead.
@router.post(
    "/ask",
    response_model=APIResponse[AIComplianceResponse],
    status_code=status.HTTP_201_CREATED,
)
def ask_ai_assistant(
    request: AIComplianceRequest,
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            resource_type="ai_assistant",
        )
    ),
    service: AIComplianceService = Depends(get_ai_compliance_service),
) -> APIResponse[AIComplianceResponse]:
    try:
        response = service.ask(request, user_id=UUID(current_user["sub"]))
    except AIProviderError as exc:
        raise service_unavailable("AI service is temporarily unavailable.") from exc
    return APIResponse(
        success=True,
        message="Question been sent to ai assistant successfully.",
        data=response,
    )


@router.get(
    "/interactions/{interaction_id}",
    response_model=APIResponse[AIInteractionResponse],
    status_code=status.HTTP_200_OK,
)
async def get_ai_interaction(
    interaction_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            resource_type="ai_assistant",
        )
    ),
) -> APIResponse[AIInteractionResponse]:
    interaction = await db.scalar(
        select(AIInteraction).where(
            AIInteraction.id == interaction_id,
            AIInteraction.tenant_id == UUID(current_user["tenant_id"]),
        )
    )
    if interaction is None:
        raise not_found("AI interaction")
    if interaction.user_id != UUID(current_user["sub"]):
        raise bad_request("You do not have access to this AI interaction.")
    return APIResponse(
        success=True,
        message="ai interaction successfully retrieved.",
        data=AIInteractionResponse.model_validate(interaction),
    )


@router.get(
    "/interactions",
    response_model=APIResponse[list[AIInteractionResponse]],
    status_code=status.HTTP_200_OK,
)
async def get_my_ai_interactions(
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            resource_type="ai_assistant",
        )
    ),
) -> APIResponse[list[AIInteractionResponse]]:
    result = await db.scalars(
        select(AIInteraction)
        .where(
            AIInteraction.tenant_id == UUID(current_user["tenant_id"]),
            AIInteraction.user_id == UUID(current_user["sub"]),
        )
        .order_by(AIInteraction.created_at.desc())
    )
    interactions = [AIInteractionResponse.model_validate(item) for item in result.all()]
    return APIResponse(
        success=True,
        message="successfully retrived all ai interactions.",
        data=interactions,
    )


@router.post(
    "/analytics/ask",
    response_model=APIResponse[AIAnalyticsResponse],
    status_code=status.HTTP_201_CREATED,
)
def ask_analytics_assistant(
    request: Request,
    question: str = Query(min_length=1, max_length=4000),
    retrieval_limit: int = Query(default=5, ge=1, le=20),
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.AUDITOR,
            resource_type="ai-analytics-assistant",
        )
    ),
    service: AIAnalyticsAssistantService = Depends(get_ai_analytics_assistant_service),
) -> APIResponse[AIAnalyticsResponse]:
    try:
        response = service.ask(
            question=question,
            user_id=UUID(current_user["sub"]),
            retrieval_limit=retrieval_limit,
        )
    except AIProviderError as exc:
        raise service_unavailable("AI service is temporarily unavailable.") from exc
    return APIResponse(
        success=True,
        message="Analytics question answered successfully.",
        data=response,
    )


@router.post(
    "/regulatory/ask",
    response_model=APIResponse[RegulatoryAssistantAnswerResponse],
    status_code=status.HTTP_200_OK,
)
def ask_regulatory_assistant(
    payload: RegulatoryAssistantRequest,
    _: dict[str, Any] = Depends(
        require_roles(*REGULATORY_ASSISTANT_ROLES, resource_type="regulatory_assistant")
    ),
    service: RegulatoryAssistantService = Depends(get_regulatory_assistant_service),
) -> APIResponse[RegulatoryAssistantAnswerResponse]:
    try:
        result = service.ask(payload)
    except AIProviderError as exc:
        raise service_unavailable(
            "AI regulatory assistant is temporarily unavailable."
        ) from exc
    return APIResponse(
        success=True,
        message="Regulatory question answered with approved knowledge sources.",
        data=result,
    )


@router.post(
    "/regulatory/search",
    response_model=APIResponse[RegulatoryAssistantSearchResponse],
    status_code=status.HTTP_200_OK,
)
def search_regulatory_knowledge(
    payload: RegulatoryAssistantRequest,
    _: dict[str, Any] = Depends(
        require_roles(*REGULATORY_ASSISTANT_ROLES, resource_type="regulatory_assistant")
    ),
    service: RegulatoryAssistantService = Depends(get_regulatory_assistant_service),
) -> APIResponse[RegulatoryAssistantSearchResponse]:
    results = service.search(payload)
    return APIResponse(
        success=True,
        message="Regulatory knowledge sources retrieved successfully.",
        data=results,
    )


_EXPLANATION_VIEW_ROLES = (
    UserRole.ADMINISTRATOR,
    UserRole.ORGANIZATION_ADMIN,
    UserRole.COMPLIANCE_MANAGER,
    UserRole.COMPLIANCE_OFFICER,
    UserRole.REVIEWER,
    UserRole.AUDITOR,
    UserRole.ANALYST,
    UserRole.VIEWER,
)

install_ai_decision_explanation_recorder()


@router.get(
    "/decision-explanations/{decision_type}/{decision_id}",
    response_model=APIResponse[AIDecisionExplanationResponse],
    status_code=status.HTTP_200_OK,
)
async def get_ai_decision_explanation(
    decision_type: str,
    decision_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            *_EXPLANATION_VIEW_ROLES, resource_type="ai_decision_explanation"
        )
    ),
) -> APIResponse[AIDecisionExplanationResponse]:
    tenant_id = UUID(current_user["tenant_id"])

    def operation(sync_db: Session):
        explanation = AIDecisionExplanationService(
            sync_db, tenant_id=tenant_id
        ).get_latest(decision_type, decision_id)
        return AIDecisionExplanationResponse.model_validate(explanation)

    explanation = await run_sync_in_tenant(db, tenant_id, operation)
    return APIResponse(
        success=True,
        message="AI decision explanation retrieved successfully.",
        data=explanation,
    )


@router.get(
    "/decision-explanations/{decision_type}/{decision_id}/history",
    response_model=APIResponse[AIDecisionExplanationHistoryResponse],
    status_code=status.HTTP_200_OK,
)
async def get_ai_decision_explanation_history(
    decision_type: str,
    decision_id: UUID,
    limit: int = Query(default=100, ge=1, le=200),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            *_EXPLANATION_VIEW_ROLES, resource_type="ai_decision_explanation"
        )
    ),
) -> APIResponse[AIDecisionExplanationHistoryResponse]:
    tenant_id = UUID(current_user["tenant_id"])

    def operation(sync_db: Session):
        items, total = AIDecisionExplanationService(
            sync_db, tenant_id=tenant_id
        ).get_history(decision_type, decision_id, limit=limit)
        return AIDecisionExplanationHistoryResponse(
            items=[
                AIDecisionExplanationResponse.model_validate(item) for item in items
            ],
            total=total,
        )

    data = await run_sync_in_tenant(db, tenant_id, operation)
    return APIResponse(
        success=True,
        message="AI decision explanation history retrieved successfully.",
        data=data,
    )
