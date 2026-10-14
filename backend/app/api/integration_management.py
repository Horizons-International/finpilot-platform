"""Tenant-scoped management API for external integrations."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.responses import APIResponse
from app.core.security import require_roles
from app.integrations.services.integration_service import IntegrationService
from app.schemas.integration import (
    IntegrationCheckResponse,
    IntegrationCreate,
    IntegrationEnabledUpdate,
    IntegrationResponse,
    IntegrationUpdate,
)
from app.utils.enums import IntegrationStatus, IntegrationType, UserRole

router = APIRouter(
    prefix="/api/v1/integrations",
    tags=["Integrations"],
)

_ADMIN_ROLES = (UserRole.ADMINISTRATOR, UserRole.ORGANIZATION_ADMIN)


def _request_metadata(request: Request) -> tuple[str | None, str | None]:
    return (
        request.client.host if request.client else None,
        request.headers.get("user-agent"),
    )


def _service(db: Session, current_user: dict[str, Any]) -> IntegrationService:
    return IntegrationService(db=db, tenant_id=UUID(current_user["tenant_id"]))


def _audit_arguments(
    request: Request,
    current_user: dict[str, Any],
) -> dict[str, Any]:
    ip_address, user_agent = _request_metadata(request)
    return {
        "user_id": UUID(current_user["sub"]),
        "email": current_user["email"],
        "ip_address": ip_address,
        "user_agent": user_agent,
    }


@router.post(
    "",
    response_model=APIResponse[IntegrationResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create integration configuration",
)
def create_integration(
    payload: IntegrationCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(*_ADMIN_ROLES, resource_type="integration")
    ),
) -> APIResponse[IntegrationResponse]:
    integration = _service(db, current_user).create(
        data=payload,
        **_audit_arguments(request, current_user),
    )
    return APIResponse(
        success=True,
        message="Integration created successfully.",
        data=IntegrationResponse.model_validate(integration),
    )


@router.get(
    "",
    response_model=APIResponse[list[IntegrationResponse]],
    summary="List integration configurations",
)
def list_integrations(
    integration_type: IntegrationType | None = Query(default=None),
    integration_status: IntegrationStatus | None = Query(default=None, alias="status"),
    is_enabled: bool | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(*_ADMIN_ROLES, resource_type="integration")
    ),
) -> APIResponse[list[IntegrationResponse]]:
    integrations = _service(db, current_user).list_all(
        integration_type=integration_type,
        status=integration_status,
        is_enabled=is_enabled,
    )
    return APIResponse(
        success=True,
        message="Integrations retrieved successfully.",
        data=[IntegrationResponse.model_validate(item) for item in integrations],
    )


@router.get(
    "/{integration_id}",
    response_model=APIResponse[IntegrationResponse],
    summary="Get integration configuration",
)
def get_integration(
    integration_id: UUID,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(*_ADMIN_ROLES, resource_type="integration")
    ),
) -> APIResponse[IntegrationResponse]:
    integration = _service(db, current_user).get_by_id(integration_id)
    return APIResponse(
        success=True,
        message="Integration retrieved successfully.",
        data=IntegrationResponse.model_validate(integration),
    )


@router.put(
    "/{integration_id}",
    response_model=APIResponse[IntegrationResponse],
    summary="Update integration configuration",
)
def update_integration(
    integration_id: UUID,
    payload: IntegrationUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(*_ADMIN_ROLES, resource_type="integration")
    ),
) -> APIResponse[IntegrationResponse]:
    integration = _service(db, current_user).update_configuration(
        integration_id=integration_id,
        data=payload,
        **_audit_arguments(request, current_user),
    )
    return APIResponse(
        success=True,
        message="Integration configuration updated successfully.",
        data=IntegrationResponse.model_validate(integration),
    )


@router.patch(
    "/{integration_id}/enabled",
    response_model=APIResponse[IntegrationResponse],
    summary="Enable or disable an integration",
)
def set_integration_enabled(
    integration_id: UUID,
    payload: IntegrationEnabledUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(*_ADMIN_ROLES, resource_type="integration")
    ),
) -> APIResponse[IntegrationResponse]:
    integration = _service(db, current_user).set_enabled(
        integration_id=integration_id,
        is_enabled=payload.is_enabled,
        **_audit_arguments(request, current_user),
    )
    return APIResponse(
        success=True,
        message=(
            "Integration enabled successfully."
            if payload.is_enabled
            else "Integration disabled successfully."
        ),
        data=IntegrationResponse.model_validate(integration),
    )


@router.post(
    "/{integration_id}/check-connection",
    response_model=APIResponse[IntegrationCheckResponse],
    summary="Check integration connectivity",
)
def check_integration_connection(
    integration_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(*_ADMIN_ROLES, resource_type="integration")
    ),
) -> APIResponse[IntegrationCheckResponse]:
    integration, message = _service(db, current_user).check_connection(
        integration_id=integration_id,
        **_audit_arguments(request, current_user),
    )
    return APIResponse(
        success=True,
        message="Integration connection check completed.",
        data=IntegrationCheckResponse(
            integration=IntegrationResponse.model_validate(integration),
            message=message,
        ),
    )
