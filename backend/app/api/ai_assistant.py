from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.ai.exceptions import AIProviderError
from app.core.responses import APIResponse
from app.core.security import require_roles
from app.schemas.ai_assistant import (
    AIComplianceRequest,
    AIComplianceResponse,
    AIInteractionResponse,
)
from app.services.ai_compliance_dependencies import get_ai_compliance_service
from app.services.ai_compliance_service import AIComplianceService
from app.utils.enums import UserRole
from app.utils.errors import service_unavailable

router = APIRouter(
    prefix="/api/v1/ai-assistant",
    tags=["AI Assistant"],
)


@router.post(
    "/ask",
    response_model=APIResponse[AIComplianceResponse],
    status_code=status.HTTP_200_OK,
)
def ask_ai_assistant(
    request: AIComplianceRequest,
    current_user: dict = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
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
)
def get_ai_interaction(
    interaction_id: UUID,
    current_user: dict = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
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
)
def get_my_ai_interactions(
    current_user: dict = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
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
