from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.ai.exceptions import AIProviderError
from app.core.database import get_db
from app.core.dependencies import (
    get_ai_analytics_assistant_service,
    get_ai_compliance_service,
    get_regulatory_assistant_service,
)
from app.core.responses import APIResponse
from app.core.security import require_roles
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
from app.services.ai_decision_explanation_service import (
    AIDecisionExplanationService,
)
from app.services.regulatory_assistant_service import RegulatoryAssistantService
from app.utils.enums import UserRole
from app.utils.errors import service_unavailable

router = APIRouter(
    prefix="/api/v1/ai-assistant",
    tags=["AI Assistant"],
)


REGULATORY_ASSISTANT_ROLES = (
    UserRole.ADMINISTRATOR,
    UserRole.COMPLIANCE_MANAGER,
    UserRole.COMPLIANCE_OFFICER,
    UserRole.REVIEWER,
    UserRole.AUDITOR,
)


@router.post(
    "/ask",
    response_model=APIResponse[AIComplianceResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Post AI question",
    description="Sends question to AI assistant.",
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
    user_id = UUID(current_user["sub"])

    try:
        response = service.ask(
            request,
            user_id=user_id,
        )
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
    summary="Get AI interaction",
    description="Retrieves AI interaction by ID.",
)
def get_ai_interaction(
    interaction_id: UUID,
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            resource_type="ai_assistant",
        )
    ),
    service: AIComplianceService = Depends(get_ai_compliance_service),
) -> APIResponse[AIInteractionResponse]:
    user_id = UUID(current_user["sub"])

    interaction = service.get_interaction(
        interaction_id,
        user_id=user_id,
    )

    return APIResponse(
        success=True,
        message="ai interaction successfully retrieved.",
        data=AIInteractionResponse.model_validate(interaction),
    )


@router.get(
    "/interactions",
    response_model=APIResponse[list[AIInteractionResponse]],
    status_code=status.HTTP_200_OK,
    summary="Get AI interactions",
    description="Retrieves all AI interactions.",
)
def get_my_ai_interactions(
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            resource_type="ai_assistant",
        )
    ),
    service: AIComplianceService = Depends(get_ai_compliance_service),
) -> APIResponse[list[AIInteractionResponse]]:
    user_id = UUID(current_user["sub"])

    interactions = service.get_user_interactions(
        user_id=user_id,
    )

    return APIResponse(
        success=True,
        message="successfully retrived all ai interactions.",
        data=[
            AIInteractionResponse.model_validate(interaction)
            for interaction in interactions
        ],
    )


@router.post(
    "/analytics/ask",
    response_model=APIResponse[AIAnalyticsResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Ask analytics AI assistant",
    description=(
        "Ask a natural-language business analytics question "
        "and receive grounded analytics insights."
    ),
)
def ask_analytics_assistant(
    request: Request,
    question: str = Query(
        min_length=1,
        max_length=4000,
        description="Natural-language analytics question.",
    ),
    retrieval_limit: int = Query(
        default=5,
        ge=1,
        le=20,
        description="Maximum number of RAG results to include.",
    ),
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.AUDITOR,
            resource_type="ai-analytics-assistant",
        )
    ),
    service: AIAnalyticsAssistantService = Depends(
        get_ai_analytics_assistant_service,
    ),
) -> APIResponse[AIAnalyticsResponse]:
    try:
        response = service.ask(
            question=question,
            user_id=UUID(current_user["sub"]),
            retrieval_limit=retrieval_limit,
        )

    except AIProviderError as exc:
        raise service_unavailable(
            "AI service is temporarily unavailable.",
        ) from exc

    return APIResponse(
        success=True,
        message="Analytics question answered successfully.",
        data=response,
    )


@router.post(
    "/regulatory/ask",
    response_model=APIResponse[RegulatoryAssistantAnswerResponse],
    status_code=status.HTTP_200_OK,
    summary="Ask the AI regulatory assistant",
    description=(
        "Answers a regulatory or compliance question using active tenant-scoped "
        "compliance policies, internal procedures, and regulatory guidelines. "
        "The response includes supporting source references."
    ),
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
    summary="Search regulatory knowledge sources",
    description=(
        "Searches active, tenant-scoped compliance policies, internal procedures, "
        "and regulatory guidelines without generating an AI answer."
    ),
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

# Importing the main AI API enables same-transaction explanation capture for
# completed decisions created by the risk, AML, document, and assistant services.
install_ai_decision_explanation_recorder()


@router.get(
    "/decision-explanations/{decision_type}/{decision_id}",
    response_model=APIResponse[AIDecisionExplanationResponse],
    status_code=status.HTTP_200_OK,
    summary="Get the explanation for an AI decision",
    description=(
        "Returns the latest stored decision rationale, contributing factors, "
        "supporting source references, risk indicators, and confidence metadata."
    ),
)
def get_ai_decision_explanation(
    decision_type: str,
    decision_id: UUID,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(*_EXPLANATION_VIEW_ROLES, resource_type="ai_decision_explanation")
    ),
) -> APIResponse[AIDecisionExplanationResponse]:
    service = AIDecisionExplanationService(
        db, tenant_id=UUID(current_user["tenant_id"])
    )
    explanation = service.get_latest(decision_type, decision_id)
    return APIResponse(
        success=True,
        message="AI decision explanation retrieved successfully.",
        data=AIDecisionExplanationResponse.model_validate(explanation),
    )


@router.get(
    "/decision-explanations/{decision_type}/{decision_id}/history",
    response_model=APIResponse[AIDecisionExplanationHistoryResponse],
    status_code=status.HTTP_200_OK,
    summary="Get explanation history for an AI decision",
    description=(
        "Returns historical explanation snapshots for one tenant-owned decision, "
        "newest first."
    ),
)
def get_ai_decision_explanation_history(
    decision_type: str,
    decision_id: UUID,
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(*_EXPLANATION_VIEW_ROLES, resource_type="ai_decision_explanation")
    ),
) -> APIResponse[AIDecisionExplanationHistoryResponse]:
    service = AIDecisionExplanationService(
        db, tenant_id=UUID(current_user["tenant_id"])
    )
    items, total = service.get_history(decision_type, decision_id, limit=limit)
    data = AIDecisionExplanationHistoryResponse(
        items=[AIDecisionExplanationResponse.model_validate(item) for item in items],
        total=total,
    )
    return APIResponse(
        success=True,
        message="AI decision explanation history retrieved successfully.",
        data=data,
    )
