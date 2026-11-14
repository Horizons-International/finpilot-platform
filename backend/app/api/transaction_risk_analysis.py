"""Async endpoints for AI transaction-risk decisions and review history."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.async_security import require_async_roles
from app.core.database import get_async_db
from app.core.responses import APIResponse
from app.schemas.transaction_risk_analysis import (
    TransactionRiskAnalysisRequest,
    TransactionRiskAnalysisResponse,
)
from app.services.async_transaction_risk_analysis_service import (
    AsyncTransactionRiskAnalysisService,
)
from app.utils.enums import UserRole

router = APIRouter(
    prefix="/api/v1/transaction-risk-analysis",
    tags=["AI Transaction Risk"],
)

_ANALYZE_ROLES = (
    UserRole.ADMINISTRATOR,
    UserRole.ORGANIZATION_ADMIN,
    UserRole.COMPLIANCE_OFFICER,
)
_VIEW_ROLES = (
    *_ANALYZE_ROLES,
    UserRole.COMPLIANCE_MANAGER,
    UserRole.REVIEWER,
    UserRole.ANALYST,
)


def _service(
    db: AsyncSession, current_user: dict[str, Any]
) -> AsyncTransactionRiskAnalysisService:
    return AsyncTransactionRiskAnalysisService(
        db, tenant_id=UUID(current_user["tenant_id"])
    )


@router.post(
    "/analyze",
    response_model=APIResponse[TransactionRiskAnalysisResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Analyze transaction patterns with AI",
    description=(
        "Compares transaction activity with recent historical behavior and customer "
        "context, stores the result, and opens a compliance review case for "
        "high/critical scores. AI scores are decision-support signals and require "
        "human review."
    ),
)
async def analyze_transaction_patterns(
    payload: TransactionRiskAnalysisRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(*_ANALYZE_ROLES, resource_type="transaction_risk_analysis")
    ),
) -> APIResponse[TransactionRiskAnalysisResponse]:
    analysis = await _service(db, current_user).analyze(
        payload,
        user_id=UUID(current_user["sub"]),
        email=str(current_user.get("email") or ""),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return APIResponse(
        success=True,
        message="AI transaction-risk analysis completed successfully.",
        data=TransactionRiskAnalysisResponse.model_validate(analysis),
    )


@router.get(
    "",
    response_model=APIResponse[list[TransactionRiskAnalysisResponse]],
    summary="List transaction-risk analysis history",
)
async def list_transaction_risk_analyses(
    customer_id: UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(*_VIEW_ROLES, resource_type="transaction_risk_analysis")
    ),
) -> APIResponse[list[TransactionRiskAnalysisResponse]]:
    items = await _service(db, current_user).list_analyses(
        customer_id=customer_id, limit=limit
    )
    return APIResponse(
        success=True,
        message="Transaction-risk analysis history retrieved successfully.",
        data=[TransactionRiskAnalysisResponse.model_validate(item) for item in items],
    )


@router.get(
    "/{analysis_id}",
    response_model=APIResponse[TransactionRiskAnalysisResponse],
    summary="Get a transaction-risk analysis",
)
async def get_transaction_risk_analysis(
    analysis_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(*_VIEW_ROLES, resource_type="transaction_risk_analysis")
    ),
) -> APIResponse[TransactionRiskAnalysisResponse]:
    analysis = await _service(db, current_user).get_analysis(analysis_id)
    return APIResponse(
        success=True,
        message="Transaction-risk analysis retrieved successfully.",
        data=TransactionRiskAnalysisResponse.model_validate(analysis),
    )
