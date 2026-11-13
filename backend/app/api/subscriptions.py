"""Native-async platform subscription and usage administration."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.async_security import require_async_platform_admin
from app.core.database import get_async_db
from app.core.responses import APIResponse
from app.schemas.subscription import (
    SubscriptionCreate,
    SubscriptionPlanResponse,
    SubscriptionResponse,
    SubscriptionUpdate,
    SubscriptionUsageResponse,
)
from app.services.async_subscription_service import AsyncSubscriptionService

router = APIRouter(prefix="/api/v1/subscriptions", tags=["Subscriptions"])


@router.get("/plans", response_model=APIResponse[list[SubscriptionPlanResponse]])
async def list_plans(
    _: dict[str, Any] = Depends(require_async_platform_admin),
) -> APIResponse[list[SubscriptionPlanResponse]]:
    return APIResponse(
        success=True,
        message="Subscription plans retrieved successfully.",
        data=[
            SubscriptionPlanResponse.model_validate(item)
            for item in AsyncSubscriptionService.plans()
        ],
    )


@router.post(
    "",
    response_model=APIResponse[SubscriptionResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_subscription(
    payload: SubscriptionCreate,
    db: AsyncSession = Depends(get_async_db),
    _: dict[str, Any] = Depends(require_async_platform_admin),
) -> APIResponse[SubscriptionResponse]:
    service = AsyncSubscriptionService(db)
    item = await service.create(
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
        data=SubscriptionResponse.model_validate(await service.serialize(item)),
    )


@router.get("", response_model=APIResponse[list[SubscriptionResponse]])
async def list_subscriptions(
    tenant_id: UUID | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_async_db),
    _: dict[str, Any] = Depends(require_async_platform_admin),
) -> APIResponse[list[SubscriptionResponse]]:
    service = AsyncSubscriptionService(db)
    rows = await service.list_subscriptions(tenant_id=tenant_id, limit=limit)
    return APIResponse(
        success=True,
        message="Subscriptions retrieved successfully.",
        data=[
            SubscriptionResponse.model_validate(await service.serialize(row))
            for row in rows
        ],
    )


@router.get("/{tenant_id}", response_model=APIResponse[SubscriptionResponse])
async def get_subscription(
    tenant_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    _: dict[str, Any] = Depends(require_async_platform_admin),
) -> APIResponse[SubscriptionResponse]:
    service = AsyncSubscriptionService(db)
    item = await service.get_latest(tenant_id)
    return APIResponse(
        success=True,
        message="Subscription retrieved successfully.",
        data=SubscriptionResponse.model_validate(await service.serialize(item)),
    )


@router.patch("/{tenant_id}", response_model=APIResponse[SubscriptionResponse])
async def update_subscription(
    tenant_id: UUID,
    payload: SubscriptionUpdate,
    db: AsyncSession = Depends(get_async_db),
    _: dict[str, Any] = Depends(require_async_platform_admin),
) -> APIResponse[SubscriptionResponse]:
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("plan_name") is not None:
        changes["plan_name"] = changes["plan_name"].value
    service = AsyncSubscriptionService(db)
    item = await service.update(tenant_id, changes)
    return APIResponse(
        success=True,
        message="Subscription updated successfully.",
        data=SubscriptionResponse.model_validate(await service.serialize(item)),
    )


@router.post("/{tenant_id}/cancel", response_model=APIResponse[SubscriptionResponse])
async def cancel_subscription(
    tenant_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    _: dict[str, Any] = Depends(require_async_platform_admin),
) -> APIResponse[SubscriptionResponse]:
    service = AsyncSubscriptionService(db)
    item = await service.cancel(tenant_id)
    return APIResponse(
        success=True,
        message="Subscription cancelled successfully.",
        data=SubscriptionResponse.model_validate(await service.serialize(item)),
    )


@router.get("/{tenant_id}/usage", response_model=APIResponse[SubscriptionUsageResponse])
async def get_subscription_usage(
    tenant_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    _: dict[str, Any] = Depends(require_async_platform_admin),
) -> APIResponse[SubscriptionUsageResponse]:
    usage = await AsyncSubscriptionService(db).get_usage(tenant_id)
    return APIResponse(
        success=True,
        message="Subscription usage retrieved successfully.",
        data=SubscriptionUsageResponse.model_validate(usage),
    )
