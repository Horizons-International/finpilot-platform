from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.async_security import require_async_roles
from app.core.database import get_async_db
from app.core.responses import APIResponse
from app.schemas.customer_onboarding import (
    CustomerOnboardingAdvanceRequest,
    CustomerOnboardingFailureRequest,
)
from app.schemas.workflow import WorkflowExecutionResponse
from app.services.async_customer_onboarding_service import (
    AsyncCustomerOnboardingService,
)
from app.utils.enums import UserRole

router = APIRouter(
    prefix="/api/v1/customers",
    tags=["Customer Onboarding"],
)


@router.post(
    "/{customer_id}/onboarding",
    response_model=APIResponse[WorkflowExecutionResponse],
)
async def start_onboarding(
    customer_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
        )
    ),
):
    service = AsyncCustomerOnboardingService(db, UUID(current_user["tenant_id"]))
    execution = await service.start(
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
async def get_onboarding(
    customer_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
        )
    ),
):
    service = AsyncCustomerOnboardingService(db, UUID(current_user["tenant_id"]))
    execution = await service.get(
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
async def advance_onboarding(
    customer_id: UUID,
    payload: CustomerOnboardingAdvanceRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
        )
    ),
):
    service = AsyncCustomerOnboardingService(db, UUID(current_user["tenant_id"]))
    execution = await service.advance(
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
async def fail_onboarding(
    customer_id: UUID,
    payload: CustomerOnboardingFailureRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
        )
    ),
):
    service = AsyncCustomerOnboardingService(db, UUID(current_user["tenant_id"]))
    execution = await service.fail(
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
async def retry_onboarding(
    customer_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
        )
    ),
):
    service = AsyncCustomerOnboardingService(db, UUID(current_user["tenant_id"]))
    execution = await service.retry(
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
