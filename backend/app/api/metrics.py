"""Async endpoints for configurable, tenant-scoped analytics metrics."""

from datetime import date
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.services.async_metric_service import AsyncMetricService
from app.core.async_security import require_async_roles
from app.core.database import get_async_db
from app.core.responses import APIResponse
from app.schemas.metrics import (
    MetricCalculationRequest,
    MetricDefinitionCreate,
    MetricDefinitionResponse,
    MetricDefinitionUpdate,
    MetricResultResponse,
)
from app.utils.enums import MetricCategory, MetricStatus, UserRole

router = APIRouter(prefix="/api/v1/metrics", tags=["Metrics"])
READ_ROLES = (
    UserRole.ADMINISTRATOR,
    UserRole.COMPLIANCE_OFFICER,
    UserRole.REVIEWER,
    UserRole.AUDITOR,
)
WRITE_ROLES = (UserRole.ADMINISTRATOR,)
CALCULATE_ROLES = (UserRole.ADMINISTRATOR, UserRole.COMPLIANCE_OFFICER)


def _service(db: AsyncSession, user: dict[str, Any]) -> AsyncMetricService:
    return AsyncMetricService(db, UUID(user["tenant_id"]))


@router.get(
    "/definitions",
    response_model=APIResponse[list[MetricDefinitionResponse]],
    summary="List metric definitions",
)
async def list_metric_definitions(
    category: MetricCategory | None = Query(default=None),
    status: MetricStatus | None = Query(default=None),
    current_user: dict[str, Any] = Depends(
        require_async_roles(*READ_ROLES, resource_type="metric")
    ),
    db: AsyncSession = Depends(get_async_db),
) -> APIResponse[list[MetricDefinitionResponse]]:
    rows = await _service(db, current_user).list_definitions(
        category=category, status=status
    )
    return APIResponse(
        success=True,
        message="Metric definitions retrieved successfully.",
        data=[MetricDefinitionResponse.model_validate(row) for row in rows],
    )


@router.get(
    "/definitions/{definition_id}",
    response_model=APIResponse[MetricDefinitionResponse],
    summary="Get metric definition",
)
async def get_metric_definition(
    definition_id: UUID,
    current_user: dict[str, Any] = Depends(
        require_async_roles(*READ_ROLES, resource_type="metric")
    ),
    db: AsyncSession = Depends(get_async_db),
) -> APIResponse[MetricDefinitionResponse]:
    row = await _service(db, current_user).get_definition(definition_id)
    return APIResponse(
        success=True,
        message="Metric definition retrieved successfully.",
        data=MetricDefinitionResponse.model_validate(row),
    )


@router.post(
    "/definitions",
    response_model=APIResponse[MetricDefinitionResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create metric definition",
)
async def create_metric_definition(
    payload: MetricDefinitionCreate,
    current_user: dict[str, Any] = Depends(
        require_async_roles(*WRITE_ROLES, resource_type="metric")
    ),
    db: AsyncSession = Depends(get_async_db),
) -> APIResponse[MetricDefinitionResponse]:
    row = await _service(db, current_user).create_definition(data=payload)
    return APIResponse(
        success=True,
        message="Metric definition created successfully.",
        data=MetricDefinitionResponse.model_validate(row),
    )


@router.put(
    "/definitions/{definition_id}",
    response_model=APIResponse[MetricDefinitionResponse],
    summary="Update metric definition",
)
async def update_metric_definition(
    definition_id: UUID,
    payload: MetricDefinitionUpdate,
    current_user: dict[str, Any] = Depends(
        require_async_roles(*WRITE_ROLES, resource_type="metric")
    ),
    db: AsyncSession = Depends(get_async_db),
) -> APIResponse[MetricDefinitionResponse]:
    row = await _service(db, current_user).update_definition(
        definition_id=definition_id, data=payload
    )
    return APIResponse(
        success=True,
        message="Metric definition updated successfully.",
        data=MetricDefinitionResponse.model_validate(row),
    )


@router.post(
    "/calculate",
    response_model=APIResponse[list[MetricResultResponse]],
    summary="Calculate and store metrics",
)
async def calculate_metrics(
    payload: MetricCalculationRequest,
    current_user: dict[str, Any] = Depends(
        require_async_roles(*CALCULATE_ROLES, resource_type="metric")
    ),
    db: AsyncSession = Depends(get_async_db),
) -> APIResponse[list[MetricResultResponse]]:
    rows = await _service(db, current_user).calculate(request=payload)
    return APIResponse(
        success=True, message="Metrics calculated and stored successfully.", data=rows
    )


@router.get(
    "/results",
    response_model=APIResponse[list[MetricResultResponse]],
    summary="Get stored metric results",
)
async def get_metric_results(
    start_date: date = Query(...),
    end_date: date = Query(...),
    category: MetricCategory | None = Query(default=None),
    metric_key: str | None = Query(default=None, min_length=1, max_length=150),
    current_user: dict[str, Any] = Depends(
        require_async_roles(*READ_ROLES, resource_type="metric")
    ),
    db: AsyncSession = Depends(get_async_db),
) -> APIResponse[list[MetricResultResponse]]:
    rows = await _service(db, current_user).get_results(
        start_date=start_date,
        end_date=end_date,
        category=category,
        metric_key=metric_key,
    )
    return APIResponse(
        success=True, message="Metric results retrieved successfully.", data=rows
    )
