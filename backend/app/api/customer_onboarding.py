from uuid import UUID

from fastapi import APIRouter, Depends, Request

from app.core.dependencies import get_customer_onboarding_service
from app.core.responses import APIResponse
from app.core.security import require_roles
from app.schemas.customer_onboarding import (
    CustomerOnboardingAdvanceRequest,
    CustomerOnboardingFailureRequest,
)
from app.schemas.workflow import WorkflowExecutionResponse
from app.services.customer_onboarding import CustomerOnboardingService
from app.utils.enums import UserRole

router = APIRouter(
    prefix="/api/v1/customers",
    tags=["Customer Onboarding"],
)


@router.post(
    "/{customer_id}/onboarding",
    response_model=APIResponse[WorkflowExecutionResponse],
)
def start_onboarding(
    customer_id: UUID,
    request: Request,
    onboarding_service: CustomerOnboardingService = Depends(
        get_customer_onboarding_service,
    ),
    current_user: dict = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
        )
    ),
):
    execution = onboarding_service.start(
        customer_id=customer_id,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
        actor_role=UserRole(current_user["role"]),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return APIResponse(
        success=True,
        message="Customer onboarding started successfully.",
        data=execution,
    )


@router.get(
    "/{customer_id}/onboarding",
    response_model=APIResponse[WorkflowExecutionResponse],
)
def get_onboarding(
    customer_id: UUID,
    onboarding_service: CustomerOnboardingService = Depends(
        get_customer_onboarding_service,
    ),
):
    execution = onboarding_service.get(
        customer_id=customer_id,
    )

    return APIResponse(
        success=True,
        message="Customer onboarding retrieved successfully.",
        data=execution,
    )


@router.post(
    "/{customer_id}/onboarding/advance",
    response_model=APIResponse[WorkflowExecutionResponse],
)
def advance_onboarding(
    customer_id: UUID,
    payload: CustomerOnboardingAdvanceRequest,
    request: Request,
    onboarding_service: CustomerOnboardingService = Depends(
        get_customer_onboarding_service,
    ),
    current_user: dict = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
        )
    ),
):
    execution = onboarding_service.advance(
        customer_id=customer_id,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
        actor_role=UserRole(current_user["role"]),
        notes=payload.notes,
        result=payload.result,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return APIResponse(
        success=True,
        message="Customer onboarding step completed successfully.",
        data=execution,
    )


@router.post(
    "/{customer_id}/onboarding/fail",
    response_model=APIResponse[WorkflowExecutionResponse],
)
def fail_onboarding(
    customer_id: UUID,
    payload: CustomerOnboardingFailureRequest,
    request: Request,
    onboarding_service: CustomerOnboardingService = Depends(
        get_customer_onboarding_service,
    ),
    current_user: dict = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
        )
    ),
):
    execution = onboarding_service.fail(
        customer_id=customer_id,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
        actor_role=UserRole(current_user["role"]),
        notes=payload.notes,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return APIResponse(
        success=True,
        message="Customer onboarding step failed.",
        data=execution,
    )


@router.post(
    "/{customer_id}/onboarding/retry",
    response_model=APIResponse[WorkflowExecutionResponse],
)
def retry_onboarding(
    customer_id: UUID,
    request: Request,
    onboarding_service: CustomerOnboardingService = Depends(
        get_customer_onboarding_service,
    ),
    current_user: dict = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
        )
    ),
):
    execution = onboarding_service.retry(
        customer_id=customer_id,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
        actor_role=UserRole(current_user["role"]),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return APIResponse(
        success=True,
        message="Customer onboarding step retry started.",
        data=execution,
    )
