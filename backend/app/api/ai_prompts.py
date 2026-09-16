from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.core.database import get_db
from app.core.responses import APIResponse
from app.core.security import require_roles
from app.schemas.ai_prompt import (
    AIPromptAssignmentCreate,
    AIPromptAssignmentResponse,
    AIPromptCreate,
    AIPromptResponse,
    AIPromptStatusUpdate,
    AIPromptVersionCreate,
)
from app.services.ai_prompt_service import AIPromptService
from app.utils.enums import AIFunction, UserRole

router = APIRouter(
    prefix="/api/v1/ai-prompts",
    tags=["AI Prompts"],
)


def get_ai_prompt_service(
    db=Depends(get_db),
) -> AIPromptService:
    return AIPromptService(db)


@router.post(
    "",
    response_model=APIResponse[AIPromptResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_ai_prompt(
    data: AIPromptCreate,
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            resource_type="ai_prompt",
        )
    ),
    service: AIPromptService = Depends(get_ai_prompt_service),
) -> APIResponse[AIPromptResponse]:
    prompt = service.create(
        data=data,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
    )

    return APIResponse(
        success=True,
        message="AI prompt created successfully.",
        data=AIPromptResponse.model_validate(prompt),
    )


@router.get(
    "",
    response_model=APIResponse[list[AIPromptResponse]],
)
def get_ai_prompts(
    _: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            resource_type="ai_prompt",
        )
    ),
    service: AIPromptService = Depends(get_ai_prompt_service),
) -> APIResponse[list[AIPromptResponse]]:
    prompts = service.get_all()

    return APIResponse(
        success=True,
        message="AI prompts retrieved successfully.",
        data=[AIPromptResponse.model_validate(prompt) for prompt in prompts],
    )


@router.get(
    "/active",
    response_model=APIResponse[list[AIPromptResponse]],
)
def get_active_ai_prompts(
    _: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            resource_type="ai_prompt",
        )
    ),
    service: AIPromptService = Depends(get_ai_prompt_service),
) -> APIResponse[list[AIPromptResponse]]:
    prompts = service.get_all_active()

    return APIResponse(
        success=True,
        message="Active AI prompts retrieved successfully.",
        data=[AIPromptResponse.model_validate(prompt) for prompt in prompts],
    )


@router.get(
    "/assignments",
    response_model=APIResponse[list[AIPromptAssignmentResponse]],
)
def get_ai_prompt_assignments(
    _: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            resource_type="ai_prompt",
        )
    ),
    service: AIPromptService = Depends(get_ai_prompt_service),
) -> APIResponse[list[AIPromptAssignmentResponse]]:
    assignments = service.get_all_assignments()

    return APIResponse(
        success=True,
        message="AI prompt assignments retrieved successfully.",
        data=[
            AIPromptAssignmentResponse.model_validate(assignment)
            for assignment in assignments
        ],
    )


@router.get(
    "/assignments/{ai_function}",
    response_model=APIResponse[AIPromptAssignmentResponse],
)
def get_ai_prompt_assignment(
    ai_function: AIFunction,
    _: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            resource_type="ai_prompt",
        )
    ),
    service: AIPromptService = Depends(get_ai_prompt_service),
) -> APIResponse[AIPromptAssignmentResponse]:
    assignment = service.get_assignment(ai_function)

    return APIResponse(
        success=True,
        message="AI prompt assignment retrieved successfully.",
        data=AIPromptAssignmentResponse.model_validate(assignment),
    )


@router.post(
    "/assignments",
    response_model=APIResponse[AIPromptAssignmentResponse],
)
def assign_ai_prompt(
    data: AIPromptAssignmentCreate,
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            resource_type="ai_prompt",
        )
    ),
    service: AIPromptService = Depends(get_ai_prompt_service),
) -> APIResponse[AIPromptAssignmentResponse]:
    assignment = service.assign(
        data=data,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
    )

    return APIResponse(
        success=True,
        message="AI prompt assigned successfully.",
        data=AIPromptAssignmentResponse.model_validate(assignment),
    )


@router.get(
    "/{prompt_id}",
    response_model=APIResponse[AIPromptResponse],
)
def get_ai_prompt(
    prompt_id: UUID,
    _: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            resource_type="ai_prompt",
        )
    ),
    service: AIPromptService = Depends(get_ai_prompt_service),
) -> APIResponse[AIPromptResponse]:
    prompt = service.get_by_id(prompt_id)

    return APIResponse(
        success=True,
        message="AI prompt retrieved successfully.",
        data=AIPromptResponse.model_validate(prompt),
    )


@router.get(
    "/{prompt_id}/versions",
    response_model=APIResponse[list[AIPromptResponse]],
)
def get_ai_prompt_versions(
    prompt_id: UUID,
    _: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            resource_type="ai_prompt",
        )
    ),
    service: AIPromptService = Depends(get_ai_prompt_service),
) -> APIResponse[list[AIPromptResponse]]:
    prompt = service.get_by_id(prompt_id)
    versions = service.get_versions(prompt.name)

    return APIResponse(
        success=True,
        message="AI prompt versions retrieved successfully.",
        data=[AIPromptResponse.model_validate(version) for version in versions],
    )


@router.post(
    "/{prompt_id}/versions",
    response_model=APIResponse[AIPromptResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_ai_prompt_version(
    prompt_id: UUID,
    data: AIPromptVersionCreate,
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            resource_type="ai_prompt",
        )
    ),
    service: AIPromptService = Depends(get_ai_prompt_service),
) -> APIResponse[AIPromptResponse]:
    prompt = service.create_version(
        prompt_id=prompt_id,
        data=data,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
    )

    return APIResponse(
        success=True,
        message="AI prompt version created successfully.",
        data=AIPromptResponse.model_validate(prompt),
    )


@router.patch(
    "/{prompt_id}/status",
    response_model=APIResponse[AIPromptResponse],
)
def update_ai_prompt_status(
    prompt_id: UUID,
    data: AIPromptStatusUpdate,
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            resource_type="ai_prompt",
        )
    ),
    service: AIPromptService = Depends(get_ai_prompt_service),
) -> APIResponse[AIPromptResponse]:
    prompt = service.update_status(
        prompt_id=prompt_id,
        data=data,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
    )

    return APIResponse(
        success=True,
        message="AI prompt status updated successfully.",
        data=AIPromptResponse.model_validate(prompt),
    )
