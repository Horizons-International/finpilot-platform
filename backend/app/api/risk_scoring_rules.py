from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.responses import APIResponse
from app.core.security import require_roles
from app.schemas.risk_scoring import (
    RiskScoringRuleCreate,
    RiskScoringRuleResponse,
    RiskScoringRuleStatusUpdate,
    RiskScoringRuleUpdate,
)
from app.services.risk_scoring_rule_service import RiskScoringRuleService
from app.utils.enums import UserRole

router = APIRouter(
    prefix="/api/v1/risk-scoring/rules",
    tags=["Risk Scoring Rules"],
)


def _service_for_tenant(
    db: Session,
    current_user: dict[str, Any],
) -> RiskScoringRuleService:
    """Create the service using only the authenticated tenant identity."""
    return RiskScoringRuleService(
        db,
        tenant_id=UUID(current_user["tenant_id"]),
    )


def _request_metadata(request: Request) -> tuple[str | None, str | None]:
    return (
        request.client.host if request.client else None,
        request.headers.get("user-agent"),
    )


@router.post(
    "",
    response_model=APIResponse[RiskScoringRuleResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create risk scoring rule",
    description=(
        "Create a configurable customer risk scoring rule. "
        "Only administrators can create risk scoring rules."
    ),
)
def create_risk_scoring_rule(
    payload: RiskScoringRuleCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(UserRole.ADMINISTRATOR, resource_type="risk_score_rule"),
    ),
) -> APIResponse[RiskScoringRuleResponse]:
    service = _service_for_tenant(db, current_user)
    ip_address, user_agent = _request_metadata(request)
    rule = service.create(
        data=payload,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
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
    status_code=status.HTTP_200_OK,
    summary="List risk scoring rules",
    description=(
        "Retrieve configured risk scoring rules. Administrators and "
        "compliance officers can access risk scoring rule configuration."
    ),
)
def list_risk_scoring_rules(
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            resource_type="risk_score_rule",
        ),
    ),
) -> APIResponse[list[RiskScoringRuleResponse]]:
    rules = _service_for_tenant(db, current_user).list_all()
    return APIResponse(
        success=True,
        message="Risk scoring rules retrieved successfully.",
        data=[RiskScoringRuleResponse.model_validate(rule) for rule in rules],
    )


@router.get(
    "/{rule_id}",
    response_model=APIResponse[RiskScoringRuleResponse],
    status_code=status.HTTP_200_OK,
    summary="Get risk scoring rule",
    description="Retrieve a single configured risk scoring rule by ID.",
)
def get_risk_scoring_rule(
    rule_id: UUID,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            resource_type="risk_score_rule",
        ),
    ),
) -> APIResponse[RiskScoringRuleResponse]:
    rule = _service_for_tenant(db, current_user).get_by_id(rule_id)
    return APIResponse(
        success=True,
        message="Risk scoring rule retrieved successfully.",
        data=RiskScoringRuleResponse.model_validate(rule),
    )


@router.put(
    "/{rule_id}",
    response_model=APIResponse[RiskScoringRuleResponse],
    status_code=status.HTTP_200_OK,
    summary="Update risk scoring rule",
    description=(
        "Update an existing risk scoring rule. "
        "Only administrators can modify risk scoring configuration."
    ),
)
def update_risk_scoring_rule(
    rule_id: UUID,
    payload: RiskScoringRuleUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(UserRole.ADMINISTRATOR, resource_type="risk_score_rule"),
    ),
) -> APIResponse[RiskScoringRuleResponse]:
    service = _service_for_tenant(db, current_user)
    ip_address, user_agent = _request_metadata(request)
    rule = service.update(
        rule_id=rule_id,
        data=payload,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
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
    status_code=status.HTTP_200_OK,
    summary="Update risk scoring rule status",
    description=(
        "Activate or deactivate a configurable risk scoring factor. "
        "Only administrators can change factor status."
    ),
)
def update_risk_scoring_rule_status(
    rule_id: UUID,
    payload: RiskScoringRuleStatusUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(UserRole.ADMINISTRATOR, resource_type="risk_score_rule"),
    ),
) -> APIResponse[RiskScoringRuleResponse]:
    service = _service_for_tenant(db, current_user)
    ip_address, user_agent = _request_metadata(request)
    rule = service.update_status(
        rule_id=rule_id,
        is_active=payload.is_active,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
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
    description=(
        "Delete a configured risk scoring rule. Only administrators can delete rules."
    ),
)
def delete_risk_scoring_rule(
    rule_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(UserRole.ADMINISTRATOR, resource_type="risk_score_rule"),
    ),
) -> APIResponse[None]:
    service = _service_for_tenant(db, current_user)
    ip_address, user_agent = _request_metadata(request)
    service.delete(
        rule_id=rule_id,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return APIResponse(
        success=True,
        message="Risk scoring rule deleted successfully.",
        data=None,
    )
