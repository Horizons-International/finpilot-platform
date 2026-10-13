from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.responses import APIResponse
from app.core.security import require_roles
from app.schemas.api_key import (
    APIKeyCreate,
    APIKeyCreatedResponse,
    APIKeyResponse,
    APIKeyUsageResponse,
)
from app.services.api_key_service import APIKeyService
from app.utils.enums import UserRole

router = APIRouter(prefix="/api/v1/api-keys", tags=["API Management"])

_ADMIN_ROLES = (UserRole.ADMINISTRATOR, UserRole.ORGANIZATION_ADMIN)


def _request_metadata(request: Request) -> tuple[str | None, str | None]:
    return (
        request.client.host if request.client else None,
        request.headers.get("user-agent"),
    )


def _service(db: Session, current_user: dict[str, Any]) -> APIKeyService:
    return APIKeyService(db, tenant_id=UUID(current_user["tenant_id"]))


@router.post(
    "",
    response_model=APIResponse[APIKeyCreatedResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Generate an API key",
    description=(
        "Creates a tenant-scoped API key. The generated secret is shown only "
        "in this response; store it securely because it cannot be retrieved later."
    ),
)
def create_api_key(
    payload: APIKeyCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(*_ADMIN_ROLES, resource_type="api_key")
    ),
) -> APIResponse[APIKeyCreatedResponse]:
    ip_address, user_agent = _request_metadata(request)
    api_key, raw_key = _service(db, current_user).create(
        data=payload,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
        ip_address=ip_address,
        user_agent=user_agent,
    )
    response_data = APIKeyCreatedResponse(
        **APIKeyResponse.model_validate(api_key).model_dump(),
        api_key=raw_key,
    )
    return APIResponse(
        success=True,
        message=(
            "API key generated successfully. Copy the secret now; "
            "it will not be shown again."
        ),
        data=response_data,
    )


@router.get(
    "",
    response_model=APIResponse[list[APIKeyResponse]],
    summary="List API keys for the current tenant",
)
def list_api_keys(
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(*_ADMIN_ROLES, resource_type="api_key")
    ),
) -> APIResponse[list[APIKeyResponse]]:
    keys = _service(db, current_user).list_all()
    return APIResponse(
        success=True,
        message="API keys retrieved successfully.",
        data=[APIKeyResponse.model_validate(key) for key in keys],
    )


@router.get(
    "/{api_key_id}/usage",
    response_model=APIResponse[list[APIKeyUsageResponse]],
    summary="View API-key usage history",
)
def list_api_key_usage(
    api_key_id: UUID,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(*_ADMIN_ROLES, resource_type="api_key")
    ),
) -> APIResponse[list[APIKeyUsageResponse]]:
    usage = _service(db, current_user).list_usage(api_key_id, limit=limit)
    return APIResponse(
        success=True,
        message="API-key usage retrieved successfully.",
        data=[APIKeyUsageResponse.model_validate(item) for item in usage],
    )


@router.post(
    "/{api_key_id}/revoke",
    response_model=APIResponse[APIKeyResponse],
    summary="Revoke an API key",
)
def revoke_api_key(
    api_key_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(*_ADMIN_ROLES, resource_type="api_key")
    ),
) -> APIResponse[APIKeyResponse]:
    ip_address, user_agent = _request_metadata(request)
    api_key = _service(db, current_user).revoke(
        api_key_id=api_key_id,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return APIResponse(
        success=True,
        message="API key revoked successfully.",
        data=APIKeyResponse.model_validate(api_key),
    )
