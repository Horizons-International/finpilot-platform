from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status

from app.core.dependencies import get_system_configuration_service
from app.core.responses import APIResponse
from app.core.security import require_roles
from app.schemas.system_configuration import (
    SystemConfigurationAuditResponse,
    SystemConfigurationCreate,
    SystemConfigurationResponse,
    SystemConfigurationStatusUpdate,
    SystemConfigurationUpdate,
)
from app.services.system_configuration_service import (
    SystemConfigurationService,
)
from app.utils.enums import (
    SystemConfigurationCategory,
    SystemConfigurationStatus,
    UserRole,
)

router = APIRouter(
    prefix="/api/v1/system-configurations",
    tags=["System Configurations"],
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
    response_model=APIResponse[SystemConfigurationResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create system configuration",
)
def create_configuration(
    payload: SystemConfigurationCreate,
    request: Request,
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            resource_type="system_configuration",
        )
    ),
    service: SystemConfigurationService = Depends(
        get_system_configuration_service,
    ),
) -> APIResponse[SystemConfigurationResponse]:
    ip_address, user_agent = _request_metadata(request)

    configuration = service.create(
        data=payload,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
        ip_address=ip_address,
        user_agent=user_agent,
    )

    return APIResponse(
        success=True,
        message="System configuration created successfully.",
        data=SystemConfigurationResponse.model_validate(
            configuration,
        ),
    )


@router.get(
    "",
    response_model=APIResponse[list[SystemConfigurationResponse]],
    status_code=status.HTTP_200_OK,
    summary="List system configurations",
)
def list_configurations(
    category: SystemConfigurationCategory | None = Query(
        default=None,
    ),
    status: SystemConfigurationStatus | None = Query(
        default=None,
    ),
    _: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            resource_type="system_configuration",
        )
    ),
    service: SystemConfigurationService = Depends(
        get_system_configuration_service,
    ),
) -> APIResponse[list[SystemConfigurationResponse]]:
    configurations = service.list_all(
        category=category,
        status=status,
    )

    return APIResponse(
        success=True,
        message="System configurations retrieved successfully.",
        data=[
            SystemConfigurationResponse.model_validate(
                configuration,
            )
            for configuration in configurations
        ],
    )


@router.get(
    "/{configuration_id}",
    response_model=APIResponse[SystemConfigurationResponse],
    status_code=status.HTTP_200_OK,
    summary="Get system configuration",
)
def get_configuration(
    configuration_id: UUID,
    _: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            resource_type="system_configuration",
        )
    ),
    service: SystemConfigurationService = Depends(
        get_system_configuration_service,
    ),
) -> APIResponse[SystemConfigurationResponse]:
    configuration = service.get_by_id(
        configuration_id,
    )

    return APIResponse(
        success=True,
        message="System configuration retrieved successfully.",
        data=SystemConfigurationResponse.model_validate(
            configuration,
        ),
    )


@router.put(
    "/{configuration_id}",
    response_model=APIResponse[SystemConfigurationResponse],
    status_code=status.HTTP_200_OK,
    summary="Update system configuration",
)
def update_configuration(
    configuration_id: UUID,
    payload: SystemConfigurationUpdate,
    request: Request,
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            resource_type="system_configuration",
        )
    ),
    service: SystemConfigurationService = Depends(
        get_system_configuration_service,
    ),
) -> APIResponse[SystemConfigurationResponse]:
    ip_address, user_agent = _request_metadata(request)

    configuration = service.update(
        configuration_id=configuration_id,
        data=payload,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
        ip_address=ip_address,
        user_agent=user_agent,
    )

    return APIResponse(
        success=True,
        message="System configuration updated successfully.",
        data=SystemConfigurationResponse.model_validate(
            configuration,
        ),
    )


@router.patch(
    "/{configuration_id}/status",
    response_model=APIResponse[SystemConfigurationResponse],
    status_code=status.HTTP_200_OK,
    summary="Activate or deactivate system configuration",
)
def update_configuration_status(
    configuration_id: UUID,
    payload: SystemConfigurationStatusUpdate,
    request: Request,
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            resource_type="system_configuration",
        )
    ),
    service: SystemConfigurationService = Depends(
        get_system_configuration_service,
    ),
) -> APIResponse[SystemConfigurationResponse]:
    ip_address, user_agent = _request_metadata(request)

    configuration = service.update_status(
        configuration_id=configuration_id,
        status=payload.status,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
        ip_address=ip_address,
        user_agent=user_agent,
    )

    return APIResponse(
        success=True,
        message="System configuration status updated successfully.",
        data=SystemConfigurationResponse.model_validate(
            configuration,
        ),
    )


@router.get(
    "/{configuration_id}/history",
    response_model=APIResponse[list[SystemConfigurationAuditResponse]],
    status_code=status.HTTP_200_OK,
    summary="Get system configuration history",
)
def get_configuration_history(
    configuration_id: UUID,
    _: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            resource_type="system_configuration",
        )
    ),
    service: SystemConfigurationService = Depends(
        get_system_configuration_service,
    ),
) -> APIResponse[list[SystemConfigurationAuditResponse]]:
    history = service.get_history(
        configuration_id,
    )

    return APIResponse(
        success=True,
        message="System configuration history retrieved successfully.",
        data=[
            SystemConfigurationAuditResponse.model_validate(
                item,
            )
            for item in history
        ],
    )
