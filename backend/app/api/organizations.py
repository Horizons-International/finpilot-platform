from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status

from app.core.dependencies import get_organization_service
from app.core.responses import APIResponse
from app.core.security import require_roles
from app.schemas.organization import (
    OrganizationCreate,
    OrganizationResponse,
    OrganizationUpdate,
)
from app.services.organization_service import OrganizationService
from app.utils.enums import UserRole

router = APIRouter(
    prefix="/api/v1/organizations",
    tags=["Organizations"],
)


def _request_metadata(
    request: Request,
) -> tuple[str | None, str | None]:
    return (
        request.client.host if request.client else None,
        request.headers.get("user-agent"),
    )


@router.post(
    "",
    response_model=APIResponse[OrganizationResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create organization",
)
def create_organization(
    payload: OrganizationCreate,
    request: Request,
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            resource_type="organization",
        )
    ),
    service: OrganizationService = Depends(
        get_organization_service,
    ),
) -> APIResponse[OrganizationResponse]:
    ip_address, user_agent = _request_metadata(request)

    organization = service.create(
        data=payload,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
        ip_address=ip_address,
        user_agent=user_agent,
    )

    return APIResponse(
        success=True,
        message="Organization created successfully.",
        data=OrganizationResponse.model_validate(
            organization,
        ),
    )


@router.get(
    "/{organization_id}",
    response_model=APIResponse[OrganizationResponse],
    status_code=status.HTTP_200_OK,
    summary="Get organization",
)
def get_organization(
    organization_id: UUID,
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            resource_type="organization",
        )
    ),
    service: OrganizationService = Depends(
        get_organization_service,
    ),
) -> APIResponse[OrganizationResponse]:
    organization = service.get(
        organization_id,
    )

    return APIResponse(
        success=True,
        message="Organization retrieved successfully.",
        data=OrganizationResponse.model_validate(
            organization,
        ),
    )


@router.put(
    "/{organization_id}",
    response_model=APIResponse[OrganizationResponse],
    status_code=status.HTTP_200_OK,
    summary="Update organization",
)
def update_organization(
    organization_id: UUID,
    payload: OrganizationUpdate,
    request: Request,
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            resource_type="organization",
        )
    ),
    service: OrganizationService = Depends(
        get_organization_service,
    ),
) -> APIResponse[OrganizationResponse]:
    ip_address, user_agent = _request_metadata(request)

    organization = service.update(
        organization_id=organization_id,
        data=payload,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
        ip_address=ip_address,
        user_agent=user_agent,
    )

    return APIResponse(
        success=True,
        message="Organization updated successfully.",
        data=OrganizationResponse.model_validate(
            organization,
        ),
    )
