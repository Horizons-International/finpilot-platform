"""Async endpoints for tenant-scoped customer risk-scoring configuration."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.async_security import require_async_roles
from app.core.database import get_async_db
from app.core.responses import APIResponse
from app.schemas.risk_scoring import (
    RiskScoringRuleCreate,
    RiskScoringRuleResponse,
    RiskScoringRuleStatusUpdate,
    RiskScoringRuleUpdate,
)
from app.services.async_risk_scoring_rule_service import AsyncRiskScoringRuleService
from app.utils.enums import UserRole

router = APIRouter(prefix="/api/v1/risk-scoring/rules", tags=["Risk Scoring Rules"])


def _service(db: AsyncSession, user: dict[str, Any]) -> AsyncRiskScoringRuleService:
    return AsyncRiskScoringRuleService(db, UUID(user["tenant_id"]))


def _request_metadata(request: Request) -> tuple[str | None, str | None]:
    return request.client.host if request.client else None, request.headers.get(
        "user-agent"
    )


@router.post(
    "",
    response_model=APIResponse[RiskScoringRuleResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create risk scoring rule",
)
async def create_risk_scoring_rule(
    payload: RiskScoringRuleCreate,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(UserRole.ADMINISTRATOR, resource_type="risk_score_rule")
    ),
) -> APIResponse[RiskScoringRuleResponse]:
    ip_address, user_agent = _request_metadata(request)
    rule = await _service(db, current_user).create(
        data=payload,
        user_id=UUID(current_user["sub"]),
        email=str(current_user.get("email") or ""),
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return APIResponse(
        success=True,
        message="Risk scoring rule created successfully.",
        data=RiskScoringRuleResponse.model_validate(rule),
    )


@router.get(
    "",
    response_model=APIResponse[list[RiskScoringRuleResponse]],
    summary="List risk scoring rules",
)
async def list_risk_scoring_rules(
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            resource_type="risk_score_rule",
        )
    ),
) -> APIResponse[list[RiskScoringRuleResponse]]:
    rows = await _service(db, current_user).list_all()
    return APIResponse(
        success=True,
        message="Risk scoring rules retrieved successfully.",
        data=[RiskScoringRuleResponse.model_validate(row) for row in rows],
    )


@router.get(
    "/{rule_id}",
    response_model=APIResponse[RiskScoringRuleResponse],
    summary="Get risk scoring rule",
)
async def get_risk_scoring_rule(
    rule_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            resource_type="risk_score_rule",
        )
    ),
) -> APIResponse[RiskScoringRuleResponse]:
    rule = await _service(db, current_user).get_by_id(rule_id)
    return APIResponse(
        success=True,
        message="Risk scoring rule retrieved successfully.",
        data=RiskScoringRuleResponse.model_validate(rule),
    )


@router.put(
    "/{rule_id}",
    response_model=APIResponse[RiskScoringRuleResponse],
    summary="Update risk scoring rule",
)
async def update_risk_scoring_rule(
    rule_id: UUID,
    payload: RiskScoringRuleUpdate,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(UserRole.ADMINISTRATOR, resource_type="risk_score_rule")
    ),
) -> APIResponse[RiskScoringRuleResponse]:
    ip_address, user_agent = _request_metadata(request)
    rule = await _service(db, current_user).update(
        rule_id=rule_id,
        data=payload,
        user_id=UUID(current_user["sub"]),
        email=str(current_user.get("email") or ""),
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return APIResponse(
        success=True,
        message="Risk scoring rule updated successfully.",
        data=RiskScoringRuleResponse.model_validate(rule),
    )


@router.patch(
    "/{rule_id}/status",
    response_model=APIResponse[RiskScoringRuleResponse],
    summary="Update risk scoring rule status",
)
async def update_risk_scoring_rule_status(
    rule_id: UUID,
    payload: RiskScoringRuleStatusUpdate,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(UserRole.ADMINISTRATOR, resource_type="risk_score_rule")
    ),
) -> APIResponse[RiskScoringRuleResponse]:
    ip_address, user_agent = _request_metadata(request)
    rule = await _service(db, current_user).update_status(
        rule_id=rule_id,
        is_active=payload.is_active,
        user_id=UUID(current_user["sub"]),
        email=str(current_user.get("email") or ""),
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return APIResponse(
        success=True,
        message="Risk scoring rule status updated successfully.",
        data=RiskScoringRuleResponse.model_validate(rule),
    )


@router.delete(
    "/{rule_id}",
    response_model=APIResponse[None],
    status_code=status.HTTP_200_OK,
    summary="Delete risk scoring rule",
)
async def delete_risk_scoring_rule(
    rule_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(UserRole.ADMINISTRATOR, resource_type="risk_score_rule")
    ),
) -> APIResponse[None]:
    ip_address, user_agent = _request_metadata(request)
    await _service(db, current_user).delete(
        rule_id=rule_id,
        user_id=UUID(current_user["sub"]),
        email=str(current_user.get("email") or ""),
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return APIResponse(
        success=True, message="Risk scoring rule deleted successfully.", data=None
    )
