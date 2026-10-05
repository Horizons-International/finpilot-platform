from datetime import date
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.analytics.services.metric_service import MetricService
from app.core.dependencies import get_metric_service
from app.core.responses import APIResponse
from app.core.security import require_roles
from app.schemas.metrics import (
    MetricCalculationRequest,
    MetricDefinitionCreate,
    MetricDefinitionResponse,
    MetricDefinitionUpdate,
    MetricResultResponse,
)
from app.utils.enums import (
    MetricCategory,
    MetricStatus,
    UserRole,
)

router = APIRouter(
    prefix="/api/v1/metrics",
    tags=["Metrics"],
)

READ_ROLES = (
    UserRole.ADMINISTRATOR,
    UserRole.COMPLIANCE_OFFICER,
    UserRole.REVIEWER,
    UserRole.AUDITOR,
)

WRITE_ROLES = (UserRole.ADMINISTRATOR,)

CALCULATE_ROLES = (
    UserRole.ADMINISTRATOR,
    UserRole.COMPLIANCE_OFFICER,
)


@router.get(
    "/definitions",
    response_model=APIResponse[list[MetricDefinitionResponse]],
    summary="List metric definitions",
)
def list_metric_definitions(
    category: MetricCategory | None = Query(
        default=None,
    ),
    status: MetricStatus | None = Query(
        default=None,
    ),
    _: dict[str, Any] = Depends(
        require_roles(
            *READ_ROLES,
            resource_type="metric",
        )
    ),
    service: MetricService = Depends(get_metric_service),
) -> APIResponse[list[MetricDefinitionResponse]]:
    definitions = service.list_definitions(
        category=category,
        status=status,
    )

    return APIResponse(
        success=True,
        message="Metric definitions retrieved successfully.",
        data=[
            MetricDefinitionResponse.model_validate(
                definition,
            )
            for definition in definitions
        ],
    )


@router.get(
    "/definitions/{definition_id}",
    response_model=APIResponse[MetricDefinitionResponse],
    summary="Get metric definition",
)
def get_metric_definition(
    definition_id: UUID,
    _: dict[str, Any] = Depends(
        require_roles(
            *READ_ROLES,
            resource_type="metric",
        )
    ),
    service: MetricService = Depends(get_metric_service),
) -> APIResponse[MetricDefinitionResponse]:
    definition = service.get_definition(
        definition_id,
    )

    return APIResponse(
        success=True,
        message="Metric definition retrieved successfully.",
        data=MetricDefinitionResponse.model_validate(
            definition,
        ),
    )


@router.post(
    "/definitions",
    response_model=APIResponse[MetricDefinitionResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create metric definition",
)
def create_metric_definition(
    payload: MetricDefinitionCreate,
    _: dict[str, Any] = Depends(
        require_roles(
            *WRITE_ROLES,
            resource_type="metric",
        )
    ),
    service: MetricService = Depends(get_metric_service),
) -> APIResponse[MetricDefinitionResponse]:
    definition = service.create_definition(
        data=payload,
    )

    return APIResponse(
        success=True,
        message="Metric definition created successfully.",
        data=MetricDefinitionResponse.model_validate(
            definition,
        ),
    )


@router.put(
    "/definitions/{definition_id}",
    response_model=APIResponse[MetricDefinitionResponse],
    summary="Update metric definition",
)
def update_metric_definition(
    definition_id: UUID,
    payload: MetricDefinitionUpdate,
    _: dict[str, Any] = Depends(
        require_roles(
            *WRITE_ROLES,
            resource_type="metric",
        )
    ),
    service: MetricService = Depends(get_metric_service),
) -> APIResponse[MetricDefinitionResponse]:
    definition = service.update_definition(
        definition_id=definition_id,
        data=payload,
    )

    return APIResponse(
        success=True,
        message="Metric definition updated successfully.",
        data=MetricDefinitionResponse.model_validate(
            definition,
        ),
    )


@router.post(
    "/calculate",
    response_model=APIResponse[list[MetricResultResponse]],
    summary="Calculate and store metrics",
)
def calculate_metrics(
    payload: MetricCalculationRequest,
    _: dict[str, Any] = Depends(
        require_roles(
            *CALCULATE_ROLES,
            resource_type="metric",
        )
    ),
    service: MetricService = Depends(get_metric_service),
) -> APIResponse[list[MetricResultResponse]]:
    results = service.calculate(
        request=payload,
    )

    return APIResponse(
        success=True,
        message="Metrics calculated and stored successfully.",
        data=results,
    )


@router.get(
    "/results",
    response_model=APIResponse[list[MetricResultResponse]],
    summary="Get stored metric results",
)
def get_metric_results(
    start_date: date = Query(...),
    end_date: date = Query(...),
    category: MetricCategory | None = Query(
        default=None,
    ),
    metric_key: str | None = Query(
        default=None,
        min_length=1,
        max_length=150,
    ),
    _: dict[str, Any] = Depends(
        require_roles(
            *READ_ROLES,
            resource_type="metric",
        )
    ),
    service: MetricService = Depends(get_metric_service),
) -> APIResponse[list[MetricResultResponse]]:
    results = service.get_results(
        start_date=start_date,
        end_date=end_date,
        category=category,
        metric_key=metric_key,
    )

    return APIResponse(
        success=True,
        message="Metric results retrieved successfully.",
        data=results,
    )
