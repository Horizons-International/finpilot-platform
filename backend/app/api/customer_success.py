"""Customer success and lifecycle-management API endpoints."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.responses import APIResponse
from app.core.security import require_roles
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
from app.services.customer_success_service import CustomerSuccessService
from app.utils.enums import UserRole

router = APIRouter(
    prefix="/api/v1/customer-success",
    tags=["Customer Success"],
)

# Keep cross-tenant relationship management restricted to the dedicated role.
# Tenant administrators must not be able to create profiles that expose another
# tenant's subscription usage merely by supplying its UUID.
_CUSTOMER_SUCCESS_ROLES = (UserRole.CUSTOMER_SUCCESS_MANAGER,)


def _service(db: Session, current_user: dict[str, Any]) -> CustomerSuccessService:
    return CustomerSuccessService(db, tenant_id=UUID(current_user["tenant_id"]))


def _actor_id(current_user: dict[str, Any]) -> UUID:
    return UUID(current_user["sub"])


@router.get(
    "/summary",
    response_model=APIResponse[CustomerSuccessSummaryResponse],
    summary="Summarize customer account health for the current tenant",
)
def get_customer_success_summary(
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(*_CUSTOMER_SUCCESS_ROLES, resource_type="customer_success")
    ),
) -> APIResponse[CustomerSuccessSummaryResponse]:
    summary = _service(db, current_user).summary()
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
def list_customer_success_profiles(
    account_status: AccountStatus | None = Query(default=None),
    health_band: HealthBand | None = Query(default=None),
    assigned_manager_id: UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(*_CUSTOMER_SUCCESS_ROLES, resource_type="customer_success")
    ),
) -> APIResponse[list[CustomerSuccessProfileResponse]]:
    profiles = _service(db, current_user).list_profiles(
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
def create_customer_success_profile(
    payload: CustomerSuccessProfileCreate,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(*_CUSTOMER_SUCCESS_ROLES, resource_type="customer_success")
    ),
) -> APIResponse[CustomerSuccessProfileResponse]:
    profile = _service(db, current_user).create_profile(
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
def get_customer_success_profile(
    profile_id: UUID,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(*_CUSTOMER_SUCCESS_ROLES, resource_type="customer_success")
    ),
) -> APIResponse[CustomerSuccessProfileResponse]:
    profile = _service(db, current_user).get_profile(profile_id)
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
def update_customer_success_profile(
    profile_id: UUID,
    payload: CustomerSuccessProfileUpdate,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(*_CUSTOMER_SUCCESS_ROLES, resource_type="customer_success")
    ),
) -> APIResponse[CustomerSuccessProfileResponse]:
    profile = _service(db, current_user).update_profile(
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
def create_usage_snapshot(
    profile_id: UUID,
    payload: CustomerSuccessUsageSnapshotCreate,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(*_CUSTOMER_SUCCESS_ROLES, resource_type="customer_success")
    ),
) -> APIResponse[CustomerSuccessUsageSnapshotResponse]:
    snapshot = _service(db, current_user).add_usage_snapshot(
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
def import_subscription_usage_snapshot(
    profile_id: UUID,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(*_CUSTOMER_SUCCESS_ROLES, resource_type="customer_success")
    ),
) -> APIResponse[CustomerSuccessUsageSnapshotResponse]:
    snapshot = _service(db, current_user).capture_subscription_usage(
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
def list_usage_snapshots(
    profile_id: UUID,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(*_CUSTOMER_SUCCESS_ROLES, resource_type="customer_success")
    ),
) -> APIResponse[list[CustomerSuccessUsageSnapshotResponse]]:
    snapshots = _service(db, current_user).list_usage(profile_id)
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
def create_support_interaction(
    profile_id: UUID,
    payload: CustomerSuccessSupportInteractionCreate,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(*_CUSTOMER_SUCCESS_ROLES, resource_type="customer_success")
    ),
) -> APIResponse[CustomerSuccessSupportInteractionResponse]:
    interaction = _service(db, current_user).add_support_interaction(
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
def list_support_interactions(
    profile_id: UUID,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(*_CUSTOMER_SUCCESS_ROLES, resource_type="customer_success")
    ),
) -> APIResponse[list[CustomerSuccessSupportInteractionResponse]]:
    interactions = _service(db, current_user).list_support_interactions(profile_id)
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
def update_support_interaction(
    profile_id: UUID,
    interaction_id: UUID,
    payload: CustomerSuccessSupportInteractionUpdate,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(*_CUSTOMER_SUCCESS_ROLES, resource_type="customer_success")
    ),
) -> APIResponse[CustomerSuccessSupportInteractionResponse]:
    interaction = _service(db, current_user).update_support_interaction(
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
def list_customer_success_history(
    profile_id: UUID,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(*_CUSTOMER_SUCCESS_ROLES, resource_type="customer_success")
    ),
) -> APIResponse[list[CustomerSuccessHistoryResponse]]:
    history = _service(db, current_user).list_history(profile_id)
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
def add_customer_success_note(
    profile_id: UUID,
    payload: CustomerSuccessNoteCreate,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(*_CUSTOMER_SUCCESS_ROLES, resource_type="customer_success")
    ),
) -> APIResponse[CustomerSuccessHistoryResponse]:
    event = _service(db, current_user).add_note(
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
def recalculate_customer_health(
    profile_id: UUID,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(*_CUSTOMER_SUCCESS_ROLES, resource_type="customer_success")
    ),
) -> APIResponse[CustomerSuccessProfileResponse]:
    profile = _service(db, current_user).recalculate_health(
        profile_id, actor_id=_actor_id(current_user)
    )
    return APIResponse(
        success=True,
        message="Customer health score recalculated successfully.",
        data=CustomerSuccessProfileResponse.model_validate(profile),
    )
