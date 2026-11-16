from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.async_security import require_async_roles
from app.core.database import get_async_db
from app.core.responses import APIResponse
from app.schemas.ai_prompt import (
    AIPromptAssignmentCreate,
    AIPromptAssignmentResponse,
    AIPromptCreate,
    AIPromptResponse,
    AIPromptStatusUpdate,
    AIPromptVersionCreate,
)
from app.services.async_ai_prompt_service import AsyncAIPromptService
from app.utils.enums import AIFunction, UserRole

router = APIRouter(prefix="/api/v1/ai-prompts", tags=["AI Prompts"])


def _service(db: AsyncSession, user: dict[str, Any]) -> AsyncAIPromptService:
    return AsyncAIPromptService(db, UUID(user["tenant_id"]))


def _metadata(request: Request) -> tuple[str | None, str | None]:
    return request.client.host if request.client else None, request.headers.get(
        "user-agent"
    )


@router.post(
    "",
    response_model=APIResponse[AIPromptResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Post AI prompt",
    description="create AI prompt.",
)
async def create_ai_prompt(
    request: Request,
    data: AIPromptCreate,
    current_user: dict[str, Any] = Depends(
        require_async_roles(UserRole.ADMINISTRATOR, resource_type="ai_prompt")
    ),
    db: AsyncSession = Depends(get_async_db),
) -> APIResponse[AIPromptResponse]:
    ip_address, user_agent = _metadata(request)
    prompt = await _service(db, current_user).create(
        data=data,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return APIResponse(
        success=True,
        message="AI prompt created successfully.",
        data=AIPromptResponse.model_validate(prompt),
    )


@router.get(
    "",
    response_model=APIResponse[list[AIPromptResponse]],
    status_code=status.HTTP_200_OK,
    summary="Get AI prompts",
    description="Retrieves all AI prompts.",
)
async def get_ai_prompts(
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            resource_type="ai_prompt",
        )
    ),
    db: AsyncSession = Depends(get_async_db),
) -> APIResponse[list[AIPromptResponse]]:
    prompts = await _service(db, current_user).get_all()
    return APIResponse(
        success=True,
        message="AI prompts retrieved successfully.",
        data=[AIPromptResponse.model_validate(item) for item in prompts],
    )


@router.get(
    "/active",
    response_model=APIResponse[list[AIPromptResponse]],
    status_code=status.HTTP_200_OK,
    summary="Get active AI prompt",
    description="Retrieves all active AI prompts.",
)
async def get_active_ai_prompts(
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            resource_type="ai_prompt",
        )
    ),
    db: AsyncSession = Depends(get_async_db),
) -> APIResponse[list[AIPromptResponse]]:
    prompts = await _service(db, current_user).get_all_active()
    return APIResponse(
        success=True,
        message="Active AI prompts retrieved successfully.",
        data=[AIPromptResponse.model_validate(item) for item in prompts],
    )


@router.get(
    "/assignments",
    response_model=APIResponse[list[AIPromptAssignmentResponse]],
    status_code=status.HTTP_200_OK,
    summary="Get AI prompt assignments",
    description="Retrieves all AI prompt assignments.",
)
async def get_ai_prompt_assignments(
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            resource_type="ai_prompt",
        )
    ),
    db: AsyncSession = Depends(get_async_db),
) -> APIResponse[list[AIPromptAssignmentResponse]]:
    assignments = await _service(db, current_user).get_all_assignments()
    return APIResponse(
        success=True,
        message="AI prompt assignments retrieved successfully.",
        data=[AIPromptAssignmentResponse.model_validate(item) for item in assignments],
    )


@router.get(
    "/assignments/{ai_function}",
    response_model=APIResponse[AIPromptAssignmentResponse],
    status_code=status.HTTP_200_OK,
    summary="Get AI prompt assignment",
    description="Retrieves AI prompt assignment by function.",
)
async def get_ai_prompt_assignment(
    ai_function: AIFunction,
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            resource_type="ai_prompt",
        )
    ),
    db: AsyncSession = Depends(get_async_db),
) -> APIResponse[AIPromptAssignmentResponse]:
    assignment = await _service(db, current_user).get_assignment(ai_function)
    return APIResponse(
        success=True,
        message="AI prompt assignment retrieved successfully.",
        data=AIPromptAssignmentResponse.model_validate(assignment),
    )


@router.post(
    "/assignments",
    response_model=APIResponse[AIPromptAssignmentResponse],
    status_code=status.HTTP_200_OK,
    summary="post AI prompt assignment",
    description="Assigns AI prompt.",
)
async def assign_ai_prompt(
    request: Request,
    data: AIPromptAssignmentCreate,
    current_user: dict[str, Any] = Depends(
        require_async_roles(UserRole.ADMINISTRATOR, resource_type="ai_prompt")
    ),
    db: AsyncSession = Depends(get_async_db),
) -> APIResponse[AIPromptAssignmentResponse]:
    ip_address, user_agent = _metadata(request)
    assignment = await _service(db, current_user).assign(
        data=data,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return APIResponse(
        success=True,
        message="AI prompt assigned successfully.",
        data=AIPromptAssignmentResponse.model_validate(assignment),
    )


@router.get(
    "/{prompt_id}",
    response_model=APIResponse[AIPromptResponse],
    status_code=status.HTTP_200_OK,
    summary="Get AI prompt",
    description="Retrieves AI prompt by ID",
)
async def get_ai_prompt(
    prompt_id: UUID,
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            resource_type="ai_prompt",
        )
    ),
    db: AsyncSession = Depends(get_async_db),
) -> APIResponse[AIPromptResponse]:
    prompt = await _service(db, current_user).get_by_id(prompt_id)
    return APIResponse(
        success=True,
        message="AI prompt retrieved successfully.",
        data=AIPromptResponse.model_validate(prompt),
    )


@router.get(
    "/{prompt_id}/versions",
    response_model=APIResponse[list[AIPromptResponse]],
    status_code=status.HTTP_200_OK,
    summary="Get AI prompt versions",
    description="Retrieves all AI prompt versions.",
)
async def get_ai_prompt_versions(
    prompt_id: UUID,
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            resource_type="ai_prompt",
        )
    ),
    db: AsyncSession = Depends(get_async_db),
) -> APIResponse[list[AIPromptResponse]]:
    service = _service(db, current_user)
    prompt = await service.get_by_id(prompt_id)
    versions = await service.get_versions(prompt.name)
    return APIResponse(
        success=True,
        message="AI prompt versions retrieved successfully.",
        data=[AIPromptResponse.model_validate(item) for item in versions],
    )


@router.post(
    "/{prompt_id}/versions",
    response_model=APIResponse[AIPromptResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Post AI prompt version",
    description="Creates AI prompt version.",
)
async def create_ai_prompt_version(
    request: Request,
    prompt_id: UUID,
    data: AIPromptVersionCreate,
    current_user: dict[str, Any] = Depends(
        require_async_roles(UserRole.ADMINISTRATOR, resource_type="ai_prompt")
    ),
    db: AsyncSession = Depends(get_async_db),
) -> APIResponse[AIPromptResponse]:
    ip_address, user_agent = _metadata(request)
    prompt = await _service(db, current_user).create_version(
        prompt_id=prompt_id,
        data=data,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return APIResponse(
        success=True,
        message="AI prompt version created successfully.",
        data=AIPromptResponse.model_validate(prompt),
    )


@router.patch(
    "/{prompt_id}/status",
    response_model=APIResponse[AIPromptResponse],
    status_code=status.HTTP_200_OK,
    summary="Patch AI prompt status",
    description="updates AI prompt status.",
)
async def update_ai_prompt_status(
    request: Request,
    prompt_id: UUID,
    data: AIPromptStatusUpdate,
    current_user: dict[str, Any] = Depends(
        require_async_roles(UserRole.ADMINISTRATOR, resource_type="ai_prompt")
    ),
    db: AsyncSession = Depends(get_async_db),
) -> APIResponse[AIPromptResponse]:
    ip_address, user_agent = _metadata(request)
    prompt = await _service(db, current_user).update_status(
        prompt_id=prompt_id,
        data=data,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return APIResponse(
        success=True,
        message="AI prompt status updated successfully.",
        data=AIPromptResponse.model_validate(prompt),
    )
