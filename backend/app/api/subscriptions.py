"""Platform-admin subscription and usage management endpoints."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.responses import APIResponse
from app.core.security import require_platform_admin
from app.schemas.subscription import (
    SubscriptionCreate,
    SubscriptionPlanResponse,
    SubscriptionResponse,
    SubscriptionUpdate,
    SubscriptionUsageResponse,
)
from app.services.subscription_service import SubscriptionService

router = APIRouter(prefix="/api/v1/subscriptions", tags=["Subscriptions"])


def _service(db: Session) -> SubscriptionService:
    return SubscriptionService(db)


@router.get(
    "/plans",
    response_model=APIResponse[list[SubscriptionPlanResponse]],
    summary="List available subscription plans",
)
def list_plans(
    _: dict[str, Any] = Depends(require_platform_admin),
) -> APIResponse[list[SubscriptionPlanResponse]]:
    return APIResponse(
        success=True,
        message="Subscription plans retrieved successfully.",
        data=[
            SubscriptionPlanResponse.model_validate(item)
            for item in SubscriptionService.plans()
        ],
    )


@router.post(
    "",
    response_model=APIResponse[SubscriptionResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create an organization subscription",
)
def create_subscription(
    payload: SubscriptionCreate,
    db: Session = Depends(get_db),
    _: dict[str, Any] = Depends(require_platform_admin),
) -> APIResponse[SubscriptionResponse]:
    subscription = _service(db).create(
        tenant_id=payload.tenant_id,
        plan_name=payload.plan_name.value,
        start_date=payload.start_date,
        end_date=payload.end_date,
        status_value=payload.status,
        usage_limits=payload.usage_limits,
    )
    return APIResponse(
        success=True,
        message="Subscription created successfully.",
        data=SubscriptionResponse.model_validate(_service(db).serialize(subscription)),
    )


@router.get(
    "",
    response_model=APIResponse[list[SubscriptionResponse]],
    summary="List organization subscriptions",
)
def list_subscriptions(
    tenant_id: UUID | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    _: dict[str, Any] = Depends(require_platform_admin),
) -> APIResponse[list[SubscriptionResponse]]:
    service = _service(db)
    subscriptions = service.list_subscriptions(tenant_id=tenant_id, limit=limit)
    return APIResponse(
        success=True,
        message="Subscriptions retrieved successfully.",
        data=[
            SubscriptionResponse.model_validate(service.serialize(item))
            for item in subscriptions
        ],
    )


@router.get(
    "/{tenant_id}",
    response_model=APIResponse[SubscriptionResponse],
    summary="Get an organization's latest subscription",
)
def get_subscription(
    tenant_id: UUID,
    db: Session = Depends(get_db),
    _: dict[str, Any] = Depends(require_platform_admin),
) -> APIResponse[SubscriptionResponse]:
    service = _service(db)
    subscription = service.get_latest(tenant_id)
    return APIResponse(
        success=True,
        message="Subscription retrieved successfully.",
        data=SubscriptionResponse.model_validate(service.serialize(subscription)),
    )


@router.patch(
    "/{tenant_id}",
    response_model=APIResponse[SubscriptionResponse],
    summary="Update an organization's subscription",
)
def update_subscription(
    tenant_id: UUID,
    payload: SubscriptionUpdate,
    db: Session = Depends(get_db),
    _: dict[str, Any] = Depends(require_platform_admin),
) -> APIResponse[SubscriptionResponse]:
    changes = payload.model_dump(exclude_unset=True)
    if "plan_name" in changes and changes["plan_name"] is not None:
        changes["plan_name"] = changes["plan_name"].value
    service = _service(db)
    subscription = service.update(tenant_id, changes)
    return APIResponse(
        success=True,
        message="Subscription updated successfully.",
        data=SubscriptionResponse.model_validate(service.serialize(subscription)),
    )


@router.post(
    "/{tenant_id}/cancel",
    response_model=APIResponse[SubscriptionResponse],
    summary="Cancel an organization's subscription",
)
def cancel_subscription(
    tenant_id: UUID,
    db: Session = Depends(get_db),
    _: dict[str, Any] = Depends(require_platform_admin),
) -> APIResponse[SubscriptionResponse]:
    service = _service(db)
    subscription = service.cancel(tenant_id)
    return APIResponse(
        success=True,
        message="Subscription cancelled successfully.",
        data=SubscriptionResponse.model_validate(service.serialize(subscription)),
    )


@router.get(
    "/{tenant_id}/usage",
    response_model=APIResponse[SubscriptionUsageResponse],
    summary="View an organization's subscription usage",
)
def get_subscription_usage(
    tenant_id: UUID,
    db: Session = Depends(get_db),
    _: dict[str, Any] = Depends(require_platform_admin),
) -> APIResponse[SubscriptionUsageResponse]:
    usage = _service(db).get_usage(tenant_id)
    return APIResponse(
        success=True,
        message="Subscription usage retrieved successfully.",
        data=SubscriptionUsageResponse.model_validate(usage),
    )
