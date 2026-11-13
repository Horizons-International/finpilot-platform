"""Native-async organization profile endpoints."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.async_security import require_async_roles
from app.core.database import get_async_db
from app.core.responses import APIResponse
from app.schemas.organization import (
    OrganizationCreate,
    OrganizationResponse,
    OrganizationUpdate,
)
from app.services.async_organization_service import AsyncOrganizationService
from app.utils.enums import UserRole

router = APIRouter(prefix="/api/v1/organizations", tags=["Organizations"])


def _meta(request: Request) -> tuple[str | None, str | None]:
    return request.client.host if request.client else None, request.headers.get(
        "user-agent"
    )


@router.post(
    "",
    response_model=APIResponse[OrganizationResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_organization(
    payload: OrganizationCreate,
    request: Request,
    current_user: dict[str, Any] = Depends(
        require_async_roles(UserRole.ADMINISTRATOR, resource_type="organization")
    ),
    db: AsyncSession = Depends(get_async_db),
) -> APIResponse[OrganizationResponse]:
    ip, agent = _meta(request)
    item = await AsyncOrganizationService(db, UUID(current_user["tenant_id"])).create(
        data=payload,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
        ip_address=ip,
        user_agent=agent,
    )
    return APIResponse(
        success=True,
        message="Organization created successfully.",
        data=OrganizationResponse.model_validate(item),
    )


@router.get(
    "/{organization_id}",
    response_model=APIResponse[OrganizationResponse],
    status_code=status.HTTP_200_OK,
)
async def get_organization(
    organization_id: UUID,
    current_user: dict[str, Any] = Depends(
        require_async_roles(UserRole.ADMINISTRATOR, resource_type="organization")
    ),
    db: AsyncSession = Depends(get_async_db),
) -> APIResponse[OrganizationResponse]:
    item = await AsyncOrganizationService(db, UUID(current_user["tenant_id"])).get(
        organization_id
    )
    return APIResponse(
        success=True,
        message="Organization retrieved successfully.",
        data=OrganizationResponse.model_validate(item),
    )


@router.put(
    "/{organization_id}",
    response_model=APIResponse[OrganizationResponse],
    status_code=status.HTTP_200_OK,
)
async def update_organization(
    organization_id: UUID,
    payload: OrganizationUpdate,
    request: Request,
    current_user: dict[str, Any] = Depends(
        require_async_roles(UserRole.ADMINISTRATOR, resource_type="organization")
    ),
    db: AsyncSession = Depends(get_async_db),
) -> APIResponse[OrganizationResponse]:
    ip, agent = _meta(request)
    item = await AsyncOrganizationService(db, UUID(current_user["tenant_id"])).update(
        organization_id=organization_id,
        data=payload,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
        ip_address=ip,
        user_agent=agent,
    )
    return APIResponse(
        success=True,
        message="Organization updated successfully.",
        data=OrganizationResponse.model_validate(item),
    )
