from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.responses import APIResponse
from app.core.security import require_roles
from app.schemas.aml_rule import (
    AMLRuleCreate,
    AMLRuleEvaluationItemResponse,
    AMLRuleEvaluationRequest,
    AMLRuleEvaluationResponse,
    AMLRuleMatchResponse,
    AMLRuleResponse,
    AMLRuleStatusUpdate,
)
from app.services.aml_rule_service import AMLRuleService
from app.utils.enums import UserRole
from app.utils.errors import unauthorized

router = APIRouter(
    prefix="/api/v1/aml-rules",
    tags=["AML Rules"],
)


def _get_authenticated_user(
    current_user: dict[str, Any],
) -> tuple[UUID, str]:
    user_id = UUID(
        current_user["sub"],
    )

    email = current_user["email"]

    if not isinstance(email, str) or not email:
        unauthorized("Authenticated user email is missing.")

    return user_id, email


def _request_metadata(
    request: Request,
) -> tuple[str | None, str | None]:
    ip_address = request.client.host if request.client else None

    user_agent = request.headers.get(
        "user-agent",
    )

    return ip_address, user_agent


@router.post(
    "",
    response_model=APIResponse[AMLRuleResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create AML rule",
    description=(
        "Create a configurable AML monitoring rule. "
        "Only administrators can create AML rules."
    ),
)
def create_aml_rule(
    payload: AMLRuleCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            resource_type="aml_rule",
        )
    ),
) -> APIResponse[AMLRuleResponse]:
    user_id, email = _get_authenticated_user(
        current_user,
    )

    ip_address, user_agent = _request_metadata(
        request,
    )

    service = AMLRuleService(db)

    rule = service.create(
        data=payload,
        user_id=user_id,
        email=email,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    return APIResponse(
        success=True,
        message="AML rule created successfully.",
        data=AMLRuleResponse.model_validate(rule),
    )


@router.get(
    "",
    response_model=APIResponse[list[AMLRuleResponse]],
    status_code=status.HTTP_200_OK,
    summary="List AML rules",
    description=(
        "List configured AML monitoring rules. "
        "Administrators and compliance officers can view rules."
    ),
)
def list_aml_rules(
    db: Session = Depends(get_db),
    _: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            resource_type="aml_rule",
        )
    ),
) -> APIResponse[list[AMLRuleResponse]]:
    service = AMLRuleService(db)

    rules = service.list_all()

    return APIResponse(
        success=True,
        message="AML rules retrieved successfully.",
        data=[AMLRuleResponse.model_validate(rule) for rule in rules],
    )


@router.post(
    "/evaluate",
    response_model=APIResponse[AMLRuleEvaluationResponse],
    status_code=status.HTTP_200_OK,
    summary="Evaluate AML rules",
    description=(
        "Evaluate active AML rules against customer, "
        "transaction, or verification data. "
        "Administrators and compliance officers can execute rules."
    ),
)
def evaluate_aml_rules(
    payload: AMLRuleEvaluationRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            resource_type="aml_rule",
        )
    ),
) -> APIResponse[AMLRuleEvaluationResponse]:
    user_id, email = _get_authenticated_user(
        current_user,
    )

    ip_address, user_agent = _request_metadata(
        request,
    )

    service = AMLRuleService(db)

    result = service.evaluate(
        rule_type=payload.rule_type,
        data=payload.data,
        user_id=user_id,
        email=email,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    response = AMLRuleEvaluationResponse(
        rule_type=result.rule_type,
        evaluated_rule_count=(result.evaluated_rule_count),
        matched_rule_count=(result.matched_rule_count),
        evaluations=[
            AMLRuleEvaluationItemResponse(
                rule_id=evaluation.rule_id,
                rule_name=evaluation.rule_name,
                rule_type=evaluation.rule_type,
                severity=evaluation.severity,
                matched=evaluation.matched,
            )
            for evaluation in result.evaluations
        ],
        matches=[
            AMLRuleMatchResponse(
                rule_id=match.rule_id,
                rule_name=match.rule_name,
                rule_type=match.rule_type,
                severity=match.severity,
                matched=match.matched,
                alert_required=match.alert_required,
            )
            for match in result.matches
        ],
    )

    return APIResponse(
        success=True,
        message="AML rules evaluated successfully.",
        data=response,
    )


@router.get(
    "/{rule_id}",
    response_model=APIResponse[AMLRuleResponse],
    status_code=status.HTTP_200_OK,
    summary="Get AML rule",
    description=(
        "Retrieve an AML rule by ID. "
        "Administrators and compliance officers can view rules."
    ),
)
def get_aml_rule(
    rule_id: UUID,
    db: Session = Depends(get_db),
    _: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            resource_type="aml_rule",
        )
    ),
) -> APIResponse[AMLRuleResponse]:
    service = AMLRuleService(db)

    rule = service.get_by_id(
        rule_id,
    )

    return APIResponse(
        success=True,
        message="AML rule retrieved successfully.",
        data=AMLRuleResponse.model_validate(rule),
    )


@router.patch(
    "/{rule_id}/status",
    response_model=APIResponse[AMLRuleResponse],
    status_code=status.HTTP_200_OK,
    summary="Activate or deactivate AML rule",
    description=(
        "Activate or deactivate an AML monitoring rule. "
        "Only administrators can change AML rule status."
    ),
)
def update_aml_rule_status(
    rule_id: UUID,
    payload: AMLRuleStatusUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(UserRole.ADMINISTRATOR, resource_type="aml_rule")
    ),
) -> APIResponse[AMLRuleResponse]:
    user_id, email = _get_authenticated_user(
        current_user,
    )

    ip_address, user_agent = _request_metadata(
        request,
    )

    service = AMLRuleService(db)

    rule = service.update_status(
        rule_id=rule_id,
        new_status=payload.status,
        user_id=user_id,
        email=email,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    return APIResponse(
        success=True,
        message="AML rule status updated successfully.",
        data=AMLRuleResponse.model_validate(rule),
    )
