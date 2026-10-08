from typing import Any

from fastapi import APIRouter, Depends, status

from app.core.dependencies import get_tenant_context, get_tenant_service
from app.core.responses import APIResponse
from app.core.security import (
    require_platform_admin,
)
from app.models.tenant import Tenant
from app.schemas.tenant import (
    TenantCreate,
    TenantResponse,
)
from app.services.tenant_service import TenantService

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
def create_tenant(
    payload: TenantCreate,
    _: dict[str, Any] = Depends(
        require_platform_admin,
    ),
    service: TenantService = Depends(
        get_tenant_service,
    ),
) -> APIResponse[TenantResponse]:
    tenant = service.create(payload)

    return APIResponse(
        success=True,
        message="Tenant created successfully.",
        data=TenantResponse.model_validate(
            tenant,
        ),
    )


@router.get(
    "/me",
    response_model=APIResponse[TenantResponse],
    summary="Get current tenant",
)
def get_current_tenant(
    tenant: Tenant = Depends(
        get_tenant_context,
    ),
) -> APIResponse[TenantResponse]:
    return APIResponse(
        success=True,
        message="Current tenant retrieved successfully.",
        data=TenantResponse.model_validate(
            tenant,
        ),
    )
