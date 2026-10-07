from typing import Any
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    Request,
    status,
)

from app.core.dependencies import (
    get_risk_prediction_service,
)
from app.core.responses import APIResponse
from app.core.security import require_roles
from app.schemas.risk_predictions import (
    RiskPredictionResponse,
)
from app.services.risk_prediction_service import (
    RiskPredictionService,
)
from app.utils.enums import UserRole

router = APIRouter(
    prefix="/api/v1/customers",
    tags=["Risk Predictions"],
)


READ_ROLES = (
    UserRole.ADMINISTRATOR,
    UserRole.COMPLIANCE_OFFICER,
    UserRole.AUDITOR,
)

CALCULATE_ROLES = (
    UserRole.ADMINISTRATOR,
    UserRole.COMPLIANCE_OFFICER,
)


@router.post(
    "/{customer_id}/risk-predictions",
    response_model=APIResponse[RiskPredictionResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create customer risk prediction",
    description=("Generate and store a predictive risk probability for a customer."),
)
def create_risk_prediction(
    customer_id: UUID,
    request: Request,
    current_user: dict[str, Any] = Depends(
        require_roles(
            *CALCULATE_ROLES,
            resource_type="risk_prediction",
        )
    ),
    service: RiskPredictionService = Depends(
        get_risk_prediction_service,
    ),
) -> APIResponse[RiskPredictionResponse]:
    prediction = service.predict_and_store(
        customer_id=customer_id,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
        ip_address=(request.client.host if request.client else None),
        user_agent=request.headers.get(
            "user-agent",
        ),
    )

    return APIResponse(
        success=True,
        message="Customer risk prediction created successfully.",
        data=RiskPredictionResponse.model_validate(
            prediction,
        ),
    )


@router.get(
    "/{customer_id}/risk-predictions/latest",
    response_model=APIResponse[RiskPredictionResponse],
    status_code=status.HTTP_200_OK,
    summary="Get latest customer risk prediction",
)
def get_latest_risk_prediction(
    customer_id: UUID,
    _: dict[str, Any] = Depends(
        require_roles(
            *READ_ROLES,
            resource_type="risk_prediction",
        )
    ),
    service: RiskPredictionService = Depends(
        get_risk_prediction_service,
    ),
) -> APIResponse[RiskPredictionResponse]:
    prediction = service.get_latest(
        customer_id=customer_id,
    )

    return APIResponse(
        success=True,
        message="Latest customer risk prediction retrieved successfully.",
        data=RiskPredictionResponse.model_validate(
            prediction,
        ),
    )


@router.get(
    "/{customer_id}/risk-predictions",
    response_model=APIResponse[list[RiskPredictionResponse]],
    status_code=status.HTTP_200_OK,
    summary="Get customer risk prediction history",
)
def get_risk_prediction_history(
    customer_id: UUID,
    _: dict[str, Any] = Depends(
        require_roles(
            *READ_ROLES,
            resource_type="risk_prediction",
        )
    ),
    service: RiskPredictionService = Depends(
        get_risk_prediction_service,
    ),
) -> APIResponse[list[RiskPredictionResponse]]:
    predictions = service.get_history(
        customer_id=customer_id,
    )

    return APIResponse(
        success=True,
        message="Customer risk prediction history retrieved successfully.",
        data=[
            RiskPredictionResponse.model_validate(
                prediction,
            )
            for prediction in predictions
        ],
    )
