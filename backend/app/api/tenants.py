"""Platform tenant registry and current-tenant endpoints."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.async_security import get_async_current_user, require_async_platform_admin
from app.core.database import get_async_db
from app.core.responses import APIResponse
from app.models.user import User
from app.schemas.tenant import TenantCreate, TenantResponse
from app.services.async_tenant_service import AsyncTenantService

router = APIRouter(
    prefix="/api/v1/tenants",
    tags=["Tenants"],
)


@router.post(
    "",
    response_model=APIResponse[TenantResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create tenant",
)
async def create_tenant(
    payload: TenantCreate,
    _: dict[str, Any] = Depends(require_async_platform_admin),
    db: AsyncSession = Depends(get_async_db),
) -> APIResponse[TenantResponse]:
    tenant = await AsyncTenantService(db).create(payload)
    return APIResponse(
        success=True,
        message="Tenant created successfully.",
        data=TenantResponse.model_validate(tenant),
    )


@router.get(
    "/me",
    response_model=APIResponse[TenantResponse],
    summary="Get current tenant",
)
async def get_current_tenant(
    current_user: User = Depends(get_async_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> APIResponse[TenantResponse]:
    tenant = await AsyncTenantService(db).get_current(UUID(str(current_user.tenant_id)))
    return APIResponse(
        success=True,
        message="Current tenant retrieved successfully.",
        data=TenantResponse.model_validate(tenant),
    )
