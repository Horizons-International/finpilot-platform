"""Customer success and lifecycle-management API endpoints."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.async_security import require_async_roles
from app.core.database import get_async_db
from app.core.responses import APIResponse
from app.schemas.customer_success import (
    AccountStatus,
    CustomerSuccessHistoryResponse,
    CustomerSuccessNoteCreate,
    CustomerSuccessProfileCreate,
    CustomerSuccessProfileResponse,
    CustomerSuccessProfileUpdate,
    CustomerSuccessSummaryResponse,
    CustomerSuccessSupportInteractionCreate,
    CustomerSuccessSupportInteractionResponse,
    CustomerSuccessSupportInteractionUpdate,
    CustomerSuccessUsageSnapshotCreate,
    CustomerSuccessUsageSnapshotResponse,
    HealthBand,
)
from app.services.async_customer_success_service import AsyncCustomerSuccessService
from app.utils.enums import UserRole

router = APIRouter(
    prefix="/api/v1/customer-success",
    tags=["Customer Success"],
)

# Keep cross-tenant relationship management restricted to the dedicated role.
# Tenant administrators must not be able to create profiles that expose another
# tenant's subscription usage merely by supplying its UUID.
_CUSTOMER_SUCCESS_ROLES = (UserRole.CUSTOMER_SUCCESS_MANAGER,)


def _service(
    db: AsyncSession, current_user: dict[str, Any]
) -> AsyncCustomerSuccessService:
    return AsyncCustomerSuccessService(db, tenant_id=UUID(current_user["tenant_id"]))


def _actor_id(current_user: dict[str, Any]) -> UUID:
    return UUID(current_user["sub"])


@router.get(
    "/summary",
    response_model=APIResponse[CustomerSuccessSummaryResponse],
    summary="Summarize customer account health for the current tenant",
)
async def get_customer_success_summary(
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(*_CUSTOMER_SUCCESS_ROLES, resource_type="customer_success")
    ),
) -> APIResponse[CustomerSuccessSummaryResponse]:
    summary = await _service(db, current_user).summary()
    return APIResponse(
        success=True,
        message="Customer success summary retrieved successfully.",
        data=CustomerSuccessSummaryResponse(**summary),
    )


@router.get(
    "",
    response_model=APIResponse[list[CustomerSuccessProfileResponse]],
    summary="List customer success accounts with lifecycle and health filters",
)
async def list_customer_success_profiles(
    account_status: AccountStatus | None = Query(default=None),
    health_band: HealthBand | None = Query(default=None),
    assigned_manager_id: UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(*_CUSTOMER_SUCCESS_ROLES, resource_type="customer_success")
    ),
) -> APIResponse[list[CustomerSuccessProfileResponse]]:
    profiles = await _service(db, current_user).list_profiles(
        account_status=account_status,
        health_band=health_band,
        assigned_manager_id=assigned_manager_id,
    )
    return APIResponse(
        success=True,
        message="Customer success profiles retrieved successfully.",
        data=[CustomerSuccessProfileResponse.model_validate(item) for item in profiles],
    )


@router.post(
    "",
    response_model=APIResponse[CustomerSuccessProfileResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create a customer lifecycle profile for an enterprise tenant",
)
async def create_customer_success_profile(
    payload: CustomerSuccessProfileCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(*_CUSTOMER_SUCCESS_ROLES, resource_type="customer_success")
    ),
) -> APIResponse[CustomerSuccessProfileResponse]:
    profile = await _service(db, current_user).create_profile(
        payload, actor_id=_actor_id(current_user)
    )
    return APIResponse(
        success=True,
        message="Customer success profile created successfully.",
        data=CustomerSuccessProfileResponse.model_validate(profile),
    )


@router.get(
    "/{profile_id}",
    response_model=APIResponse[CustomerSuccessProfileResponse],
    summary="Get customer lifecycle profile and current health score",
)
async def get_customer_success_profile(
    profile_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(*_CUSTOMER_SUCCESS_ROLES, resource_type="customer_success")
    ),
) -> APIResponse[CustomerSuccessProfileResponse]:
    profile = await _service(db, current_user).get_profile(profile_id)
    return APIResponse(
        success=True,
        message="Customer success profile retrieved successfully.",
        data=CustomerSuccessProfileResponse.model_validate(profile),
    )


@router.patch(
    "/{profile_id}",
    response_model=APIResponse[CustomerSuccessProfileResponse],
    summary="Update account status, implementation stage, manager or success plan",
)
async def update_customer_success_profile(
    profile_id: UUID,
    payload: CustomerSuccessProfileUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(*_CUSTOMER_SUCCESS_ROLES, resource_type="customer_success")
    ),
) -> APIResponse[CustomerSuccessProfileResponse]:
    profile = await _service(db, current_user).update_profile(
        profile_id, payload, actor_id=_actor_id(current_user)
    )
    return APIResponse(
        success=True,
        message="Customer success profile updated successfully.",
        data=CustomerSuccessProfileResponse.model_validate(profile),
    )


@router.post(
    "/{profile_id}/usage-snapshots",
    response_model=APIResponse[CustomerSuccessUsageSnapshotResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Record a time-bounded customer product-usage snapshot",
)
async def create_usage_snapshot(
    profile_id: UUID,
    payload: CustomerSuccessUsageSnapshotCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(*_CUSTOMER_SUCCESS_ROLES, resource_type="customer_success")
    ),
) -> APIResponse[CustomerSuccessUsageSnapshotResponse]:
    snapshot = await _service(db, current_user).add_usage_snapshot(
        profile_id, payload, actor_id=_actor_id(current_user)
    )
    return APIResponse(
        success=True,
        message="Customer usage snapshot recorded successfully.",
        data=CustomerSuccessUsageSnapshotResponse.model_validate(snapshot),
    )


@router.post(
    "/{profile_id}/usage-snapshots/from-subscription",
    response_model=APIResponse[CustomerSuccessUsageSnapshotResponse],
    status_code=status.HTTP_201_CREATED,
    summary=(
        "Import current-month usage from the linked customer's subscription records"
    ),
)
async def import_subscription_usage_snapshot(
    profile_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(*_CUSTOMER_SUCCESS_ROLES, resource_type="customer_success")
    ),
) -> APIResponse[CustomerSuccessUsageSnapshotResponse]:
    snapshot = await _service(db, current_user).capture_subscription_usage(
        profile_id, actor_id=_actor_id(current_user)
    )
    return APIResponse(
        success=True,
        message="Current-month subscription usage imported successfully.",
        data=CustomerSuccessUsageSnapshotResponse.model_validate(snapshot),
    )


@router.get(
    "/{profile_id}/usage-snapshots",
    response_model=APIResponse[list[CustomerSuccessUsageSnapshotResponse]],
    summary="List historical usage snapshots for an account",
)
async def list_usage_snapshots(
    profile_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(*_CUSTOMER_SUCCESS_ROLES, resource_type="customer_success")
    ),
) -> APIResponse[list[CustomerSuccessUsageSnapshotResponse]]:
    snapshots = await _service(db, current_user).list_usage(profile_id)
    return APIResponse(
        success=True,
        message="Customer usage history retrieved successfully.",
        data=[
            CustomerSuccessUsageSnapshotResponse.model_validate(item)
            for item in snapshots
        ],
    )


@router.post(
    "/{profile_id}/support-interactions",
    response_model=APIResponse[CustomerSuccessSupportInteractionResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Record a support case or customer interaction",
)
async def create_support_interaction(
    profile_id: UUID,
    payload: CustomerSuccessSupportInteractionCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(*_CUSTOMER_SUCCESS_ROLES, resource_type="customer_success")
    ),
) -> APIResponse[CustomerSuccessSupportInteractionResponse]:
    interaction = await _service(db, current_user).add_support_interaction(
        profile_id, payload, actor_id=_actor_id(current_user)
    )
    return APIResponse(
        success=True,
        message="Customer support interaction recorded successfully.",
        data=CustomerSuccessSupportInteractionResponse.model_validate(interaction),
    )


@router.get(
    "/{profile_id}/support-interactions",
    response_model=APIResponse[list[CustomerSuccessSupportInteractionResponse]],
    summary="List support and customer touchpoint history",
)
async def list_support_interactions(
    profile_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(*_CUSTOMER_SUCCESS_ROLES, resource_type="customer_success")
    ),
) -> APIResponse[list[CustomerSuccessSupportInteractionResponse]]:
    interactions = await _service(db, current_user).list_support_interactions(
        profile_id
    )
    return APIResponse(
        success=True,
        message="Customer support history retrieved successfully.",
        data=[
            CustomerSuccessSupportInteractionResponse.model_validate(item)
            for item in interactions
        ],
    )


@router.patch(
    "/{profile_id}/support-interactions/{interaction_id}",
    response_model=APIResponse[CustomerSuccessSupportInteractionResponse],
    summary="Update support severity, status, assignee or resolution details",
)
async def update_support_interaction(
    profile_id: UUID,
    interaction_id: UUID,
    payload: CustomerSuccessSupportInteractionUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(*_CUSTOMER_SUCCESS_ROLES, resource_type="customer_success")
    ),
) -> APIResponse[CustomerSuccessSupportInteractionResponse]:
    interaction = await _service(db, current_user).update_support_interaction(
        profile_id,
        interaction_id,
        payload,
        actor_id=_actor_id(current_user),
    )
    return APIResponse(
        success=True,
        message="Customer support interaction updated successfully.",
        data=CustomerSuccessSupportInteractionResponse.model_validate(interaction),
    )


@router.get(
    "/{profile_id}/history",
    response_model=APIResponse[list[CustomerSuccessHistoryResponse]],
    summary="Get the append-only relationship timeline",
)
async def list_customer_success_history(
    profile_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(*_CUSTOMER_SUCCESS_ROLES, resource_type="customer_success")
    ),
) -> APIResponse[list[CustomerSuccessHistoryResponse]]:
    history = await _service(db, current_user).list_history(profile_id)
    return APIResponse(
        success=True,
        message="Customer relationship history retrieved successfully.",
        data=[CustomerSuccessHistoryResponse.model_validate(item) for item in history],
    )


@router.post(
    "/{profile_id}/notes",
    response_model=APIResponse[CustomerSuccessHistoryResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Add an immutable customer relationship note",
)
async def add_customer_success_note(
    profile_id: UUID,
    payload: CustomerSuccessNoteCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(*_CUSTOMER_SUCCESS_ROLES, resource_type="customer_success")
    ),
) -> APIResponse[CustomerSuccessHistoryResponse]:
    event = await _service(db, current_user).add_note(
        profile_id, payload, actor_id=_actor_id(current_user)
    )
    return APIResponse(
        success=True,
        message="Customer relationship note recorded successfully.",
        data=CustomerSuccessHistoryResponse.model_validate(event),
    )


@router.post(
    "/{profile_id}/recalculate-health",
    response_model=APIResponse[CustomerSuccessProfileResponse],
    summary=(
        "Recalculate the customer health score using current lifecycle, usage "
        "and support data"
    ),
)
async def recalculate_customer_health(
    profile_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(*_CUSTOMER_SUCCESS_ROLES, resource_type="customer_success")
    ),
) -> APIResponse[CustomerSuccessProfileResponse]:
    profile = await _service(db, current_user).recalculate_health(
        profile_id, actor_id=_actor_id(current_user)
    )
    return APIResponse(
        success=True,
        message="Customer health score recalculated successfully.",
        data=CustomerSuccessProfileResponse.model_validate(profile),
    )
