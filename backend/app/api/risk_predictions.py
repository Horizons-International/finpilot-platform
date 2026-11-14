"""Async customer risk-prediction endpoints."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.async_security import require_async_roles
from app.core.database import get_async_db
from app.core.responses import APIResponse
from app.schemas.risk_predictions import RiskPredictionResponse
from app.services.async_risk_prediction_service import AsyncRiskPredictionService
from app.utils.enums import UserRole

router = APIRouter(prefix="/api/v1/customers", tags=["Risk Predictions"])

READ_ROLES = (
    UserRole.ADMINISTRATOR,
    UserRole.COMPLIANCE_OFFICER,
    UserRole.AUDITOR,
)
CALCULATE_ROLES = (UserRole.ADMINISTRATOR, UserRole.COMPLIANCE_OFFICER)


def _service(db: AsyncSession, user: dict[str, Any]) -> AsyncRiskPredictionService:
    return AsyncRiskPredictionService(db, tenant_id=UUID(user["tenant_id"]))


@router.post(
    "/{customer_id}/risk-predictions",
    response_model=APIResponse[RiskPredictionResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create customer risk prediction",
    description="Generate and store a predictive risk probability for a customer.",
)
async def create_risk_prediction(
    customer_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(*CALCULATE_ROLES, resource_type="risk_prediction")
    ),
) -> APIResponse[RiskPredictionResponse]:
    prediction = await _service(db, current_user).predict_and_store(
        customer_id=customer_id,
        user_id=UUID(current_user["sub"]),
        email=str(current_user.get("email") or ""),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return APIResponse(
        success=True,
        message="Customer risk prediction created successfully.",
        data=RiskPredictionResponse.model_validate(prediction),
    )


@router.get(
    "/{customer_id}/risk-predictions/latest",
    response_model=APIResponse[RiskPredictionResponse],
    status_code=status.HTTP_200_OK,
    summary="Get latest customer risk prediction",
)
async def get_latest_risk_prediction(
    customer_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(*READ_ROLES, resource_type="risk_prediction")
    ),
) -> APIResponse[RiskPredictionResponse]:
    prediction = await _service(db, current_user).get_latest(customer_id=customer_id)
    return APIResponse(
        success=True,
        message="Latest customer risk prediction retrieved successfully.",
        data=RiskPredictionResponse.model_validate(prediction),
    )


@router.get(
    "/{customer_id}/risk-predictions",
    response_model=APIResponse[list[RiskPredictionResponse]],
    status_code=status.HTTP_200_OK,
    summary="Get customer risk prediction history",
)
async def get_risk_prediction_history(
    customer_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(*READ_ROLES, resource_type="risk_prediction")
    ),
) -> APIResponse[list[RiskPredictionResponse]]:
    predictions = await _service(db, current_user).get_history(customer_id=customer_id)
    return APIResponse(
        success=True,
        message="Customer risk prediction history retrieved successfully.",
        data=[RiskPredictionResponse.model_validate(item) for item in predictions],
    )
