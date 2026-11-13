"""Native-async API key management endpoints."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.async_security import require_async_roles
from app.core.database import get_async_db
from app.core.responses import APIResponse
from app.schemas.api_key import (
    APIKeyCreate,
    APIKeyCreatedResponse,
    APIKeyResponse,
    APIKeyUsageResponse,
)
from app.services.async_platform_integration_service import AsyncAPIKeyService
from app.utils.enums import UserRole

router = APIRouter(prefix="/api/v1/api-keys", tags=["API Management"])
_ADMIN_ROLES = (UserRole.ADMINISTRATOR, UserRole.ORGANIZATION_ADMIN)


def _service(db: AsyncSession, user: dict[str, Any]) -> AsyncAPIKeyService:
    return AsyncAPIKeyService(db, UUID(user["tenant_id"]))


def _metadata(request: Request) -> tuple[str | None, str | None]:
    return request.client.host if request.client else None, request.headers.get(
        "user-agent"
    )


@router.post(
    "",
    response_model=APIResponse[APIKeyCreatedResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Generate an API key",
    description=(
        "The generated secret is shown only in this response. Store it securely."
    ),
)
async def create_api_key(
    payload: APIKeyCreate,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(*_ADMIN_ROLES, resource_type="api_key")
    ),
) -> APIResponse[APIKeyCreatedResponse]:
    ip, agent = _metadata(request)
    item, raw = await _service(db, current_user).create(
        data=payload,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
        ip_address=ip,
        user_agent=agent,
    )
    data = APIKeyCreatedResponse(
        **APIKeyResponse.model_validate(item).model_dump(), api_key=raw
    )
    return APIResponse(
        success=True,
        message=(
            "API key generated successfully. Copy the secret "
            "now; it will not be shown again."
        ),
        data=data,
    )


@router.get("", response_model=APIResponse[list[APIKeyResponse]])
async def list_api_keys(
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(*_ADMIN_ROLES, resource_type="api_key")
    ),
) -> APIResponse[list[APIKeyResponse]]:
    rows = await _service(db, current_user).list_all()
    return APIResponse(
        success=True,
        message="API keys retrieved successfully.",
        data=[APIKeyResponse.model_validate(row) for row in rows],
    )


@router.get(
    "/{api_key_id}/usage", response_model=APIResponse[list[APIKeyUsageResponse]]
)
async def list_api_key_usage(
    api_key_id: UUID,
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(*_ADMIN_ROLES, resource_type="api_key")
    ),
) -> APIResponse[list[APIKeyUsageResponse]]:
    rows = await _service(db, current_user).list_usage(api_key_id, limit=limit)
    return APIResponse(
        success=True,
        message="API-key usage retrieved successfully.",
        data=[APIKeyUsageResponse.model_validate(row) for row in rows],
    )


@router.post("/{api_key_id}/revoke", response_model=APIResponse[APIKeyResponse])
async def revoke_api_key(
    api_key_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(*_ADMIN_ROLES, resource_type="api_key")
    ),
) -> APIResponse[APIKeyResponse]:
    ip, agent = _metadata(request)
    item = await _service(db, current_user).revoke(
        api_key_id=api_key_id,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
        ip_address=ip,
        user_agent=agent,
    )
    return APIResponse(
        success=True,
        message="API key revoked successfully.",
        data=APIKeyResponse.model_validate(item),
    )
