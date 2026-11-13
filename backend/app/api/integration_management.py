"""Native-async tenant-scoped management API for external integrations."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.async_security import require_async_roles
from app.core.database import get_async_db
from app.core.responses import APIResponse
from app.schemas.integration import (
    IntegrationCheckResponse,
    IntegrationCreate,
    IntegrationEnabledUpdate,
    IntegrationResponse,
    IntegrationUpdate,
)
from app.services.async_platform_integration_service import AsyncIntegrationService
from app.utils.enums import IntegrationStatus, IntegrationType, UserRole

router = APIRouter(prefix="/api/v1/integrations", tags=["Integrations"])
_ADMIN_ROLES = (UserRole.ADMINISTRATOR, UserRole.ORGANIZATION_ADMIN)


def _metadata(request: Request) -> tuple[str | None, str | None]:
    return request.client.host if request.client else None, request.headers.get(
        "user-agent"
    )


def _actor(request: Request, user: dict[str, Any]) -> dict[str, Any]:
    ip, agent = _metadata(request)
    return {
        "user_id": UUID(user["sub"]),
        "email": user["email"],
        "ip_address": ip,
        "user_agent": agent,
    }


def _service(db: AsyncSession, user: dict[str, Any]) -> AsyncIntegrationService:
    return AsyncIntegrationService(db, UUID(user["tenant_id"]))


@router.post(
    "",
    response_model=APIResponse[IntegrationResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_integration(
    payload: IntegrationCreate,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(*_ADMIN_ROLES, resource_type="integration")
    ),
) -> APIResponse[IntegrationResponse]:
    item = await _service(db, current_user).create(
        data=payload, **_actor(request, current_user)
    )
    return APIResponse(
        success=True,
        message="Integration created successfully.",
        data=IntegrationResponse.model_validate(item),
    )


@router.get("", response_model=APIResponse[list[IntegrationResponse]])
async def list_integrations(
    integration_type: IntegrationType | None = Query(default=None),
    integration_status: IntegrationStatus | None = Query(default=None, alias="status"),
    is_enabled: bool | None = Query(default=None),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(*_ADMIN_ROLES, resource_type="integration")
    ),
) -> APIResponse[list[IntegrationResponse]]:
    rows = await _service(db, current_user).list_all(
        integration_type=integration_type,
        status=integration_status,
        is_enabled=is_enabled,
    )
    return APIResponse(
        success=True,
        message="Integrations retrieved successfully.",
        data=[IntegrationResponse.model_validate(row) for row in rows],
    )


@router.get("/{integration_id}", response_model=APIResponse[IntegrationResponse])
async def get_integration(
    integration_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(*_ADMIN_ROLES, resource_type="integration")
    ),
) -> APIResponse[IntegrationResponse]:
    item = await _service(db, current_user).get_by_id(integration_id)
    return APIResponse(
        success=True,
        message="Integration retrieved successfully.",
        data=IntegrationResponse.model_validate(item),
    )


@router.put("/{integration_id}", response_model=APIResponse[IntegrationResponse])
async def update_integration(
    integration_id: UUID,
    payload: IntegrationUpdate,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(*_ADMIN_ROLES, resource_type="integration")
    ),
) -> APIResponse[IntegrationResponse]:
    item = await _service(db, current_user).update_configuration(
        integration_id=integration_id, data=payload, **_actor(request, current_user)
    )
    return APIResponse(
        success=True,
        message="Integration configuration updated successfully.",
        data=IntegrationResponse.model_validate(item),
    )


@router.patch(
    "/{integration_id}/enabled", response_model=APIResponse[IntegrationResponse]
)
async def set_integration_enabled(
    integration_id: UUID,
    payload: IntegrationEnabledUpdate,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(*_ADMIN_ROLES, resource_type="integration")
    ),
) -> APIResponse[IntegrationResponse]:
    item = await _service(db, current_user).set_enabled(
        integration_id=integration_id,
        is_enabled=payload.is_enabled,
        **_actor(request, current_user),
    )
    message = (
        "Integration enabled successfully."
        if payload.is_enabled
        else "Integration disabled successfully."
    )
    return APIResponse(
        success=True, message=message, data=IntegrationResponse.model_validate(item)
    )


@router.post(
    "/{integration_id}/check-connection",
    response_model=APIResponse[IntegrationCheckResponse],
)
async def check_integration_connection(
    integration_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(*_ADMIN_ROLES, resource_type="integration")
    ),
) -> APIResponse[IntegrationCheckResponse]:
    item, message = await _service(db, current_user).check_connection(
        integration_id=integration_id, **_actor(request, current_user)
    )
    return APIResponse(
        success=True,
        message="Integration connection check completed.",
        data=IntegrationCheckResponse(
            integration=IntegrationResponse.model_validate(item), message=message
        ),
    )
