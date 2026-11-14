"""Native-async routes for AI-supported AML investigation analysis and history."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.exceptions import AIProviderError
from app.core.async_security import require_async_roles
from app.core.database import get_async_db
from app.core.responses import APIResponse
from app.schemas.aml_investigation_assistant import (
    AMLInvestigationAnalysisListResponse,
    AMLInvestigationAnalysisRequest,
    AMLInvestigationAnalysisResponse,
)
from app.services.async_aml_investigation_assistant_service import (
    AsyncAMLInvestigationAssistantService,
)
from app.utils.enums import UserRole
from app.utils.errors import service_unavailable

router = APIRouter(
    prefix="/api/v1/ai-assistant/aml-investigations",
    tags=["AI AML Investigations"],
)

_INVESTIGATOR_ROLES = (
    UserRole.ADMINISTRATOR,
    UserRole.COMPLIANCE_OFFICER,
    UserRole.REVIEWER,
)


def _service(
    db: AsyncSession,
    current_user: dict[str, Any],
) -> AsyncAMLInvestigationAssistantService:
    return AsyncAMLInvestigationAssistantService(
        db,
        tenant_id=UUID(current_user["tenant_id"]),
    )


@router.post(
    "/analyze",
    response_model=APIResponse[AMLInvestigationAnalysisResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Analyze an AML investigation",
    description=(
        "Builds a tenant-scoped evidence pack from customer, transaction, anomaly, "
        "rule-monitoring, verification, and compliance data; retrieves relevant "
        "compliance knowledge asynchronously; then stores a structured AI-assisted "
        "review."
    ),
)
async def analyze_aml_investigation(
    payload: AMLInvestigationAnalysisRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(*_INVESTIGATOR_ROLES, resource_type="aml_investigation")
    ),
) -> APIResponse[AMLInvestigationAnalysisResponse]:
    try:
        result = await _service(db, current_user).analyze(
            payload,
            user_id=UUID(current_user["sub"]),
        )
    except AIProviderError as exc:
        raise service_unavailable(
            "AI service is temporarily unavailable. "
            "The investigation record has been retained."
        ) from exc
    return APIResponse(
        success=True,
        message="AML investigation analysis completed successfully.",
        data=result,
    )


@router.get(
    "",
    response_model=APIResponse[AMLInvestigationAnalysisListResponse],
    summary="List AML investigation analysis history",
)
async def list_aml_investigation_analyses(
    customer_id: UUID | None = Query(default=None),
    compliance_case_id: UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(*_INVESTIGATOR_ROLES, resource_type="aml_investigation")
    ),
) -> APIResponse[AMLInvestigationAnalysisListResponse]:
    result = await _service(db, current_user).list_history(
        customer_id=customer_id,
        compliance_case_id=compliance_case_id,
        limit=limit,
    )
    return APIResponse(
        success=True,
        message="AML investigation history retrieved successfully.",
        data=result,
    )


@router.get(
    "/{analysis_id}",
    response_model=APIResponse[AMLInvestigationAnalysisResponse],
    summary="Get an AML investigation analysis",
)
async def get_aml_investigation_analysis(
    analysis_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(*_INVESTIGATOR_ROLES, resource_type="aml_investigation")
    ),
) -> APIResponse[AMLInvestigationAnalysisResponse]:
    result = await _service(db, current_user).get_history_item(analysis_id)
    return APIResponse(
        success=True,
        message="AML investigation analysis retrieved successfully.",
        data=result,
    )
