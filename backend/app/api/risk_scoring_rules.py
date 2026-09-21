from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.responses import APIResponse
from app.core.security import require_roles
from app.schemas.risk_scoring import (
    RiskScoringRuleCreate,
    RiskScoringRuleResponse,
    RiskScoringRuleUpdate,
)
from app.services.risk_scoring_rule_service import RiskScoringRuleService
from app.utils.enums import UserRole

router = APIRouter(
    prefix="/api/v1/risk-scoring/rules",
    tags=["Risk Scoring Rules"],
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
    current_user: dict = Depends(
        require_roles(UserRole.ADMINISTRATOR),
    ),
) -> APIResponse[RiskScoringRuleResponse]:
    service = RiskScoringRuleService(db)

    user_id = UUID(current_user["sub"])
    email = current_user["email"]

    rule = service.create(
        data=payload,
        user_id=user_id,
        email=email,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
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
        "Retrieve configured risk scoring rules. "
        "Administrators and compliance officers can access "
        "risk scoring rule configuration."
    ),
)
def list_risk_scoring_rules(
    db: Session = Depends(get_db),
    current_user: dict = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
        ),
    ),
) -> APIResponse[list[RiskScoringRuleResponse]]:
    service = RiskScoringRuleService(db)

    rules = service.get_all()

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
    description=(
        "Retrieve a single configured risk scoring rule by its unique identifier."
    ),
)
def get_risk_scoring_rule(
    rule_id: UUID,
    db: Session = Depends(get_db),
    current_user: dict = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
        ),
    ),
) -> APIResponse[RiskScoringRuleResponse]:
    service = RiskScoringRuleService(db)

    rule = service.get_by_id(rule_id)

    return APIResponse(
        success=True,
        message="Risk scoring rule retrieved successfully.",
        data=RiskScoringRuleResponse.model_validate(rule),
    )


@router.patch(
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
    current_user: dict = Depends(
        require_roles(UserRole.ADMINISTRATOR),
    ),
) -> APIResponse[RiskScoringRuleResponse]:
    service = RiskScoringRuleService(db)

    user_id = UUID(current_user["sub"])
    email = current_user["email"]

    rule = service.update(
        rule_id=rule_id,
        data=payload,
        user_id=user_id,
        email=email,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
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
        "Enable or disable an existing risk scoring rule. "
        "Only administrators can modify risk scoring rule status."
    ),
)
def update_risk_scoring_rule_status(
    rule_id: UUID,
    is_active: bool,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(
        require_roles(UserRole.ADMINISTRATOR),
    ),
) -> APIResponse[RiskScoringRuleResponse]:
    service = RiskScoringRuleService(db)

    user_id = UUID(current_user["sub"])
    email = current_user["email"]

    rule = service.update_status(
        rule_id=rule_id,
        is_active=is_active,
        user_id=user_id,
        email=email,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
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
        "Delete a configured risk scoring rule. "
        "Only administrators can delete risk scoring rules."
    ),
)
def delete_risk_scoring_rule(
    rule_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(
        require_roles(UserRole.ADMINISTRATOR),
    ),
) -> APIResponse[None]:
    service = RiskScoringRuleService(db)

    user_id = UUID(current_user["sub"])
    email = current_user["email"]

    service.delete(
        rule_id=rule_id,
        user_id=user_id,
        email=email,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return APIResponse(
        success=True,
        message="Risk scoring rule deleted successfully.",
        data=None,
    )
