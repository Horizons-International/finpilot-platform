"""Native-async tenant-scoped transaction anomaly endpoints."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.async_security import require_async_roles
from app.core.database import get_async_db
from app.core.responses import APIResponse
from app.schemas.transaction_anomaly import (
    TransactionAnomalyAnalysisRequest,
    TransactionAnomalyAnalysisResponse,
    TransactionAnomalyResponse,
)
from app.services.async_transaction_anomaly_service import (
    AsyncTransactionAnomalyService,
)
from app.utils.enums import UserRole

router = APIRouter(
    prefix="/api/v1/transaction-anomalies",
    tags=["Transaction Anomaly Detection"],
)


@router.post(
    "/analyze",
    response_model=APIResponse[TransactionAnomalyAnalysisResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Analyze customer transaction activity for anomalies",
    description=(
        "Compare a new transaction batch with retained and caller-supplied "
        "historical activity. Findings are investigative signals, not proof "
        "of wrongdoing."
    ),
)
async def analyze_transaction_anomalies(
    payload: TransactionAnomalyAnalysisRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            resource_type="transaction_anomaly",
        )
    ),
) -> APIResponse[TransactionAnomalyAnalysisResponse]:
    service = AsyncTransactionAnomalyService(
        db,
        tenant_id=UUID(current_user["tenant_id"]),
    )
    anomalies, message = await service.analyze(payload)
    data = TransactionAnomalyAnalysisResponse(
        customer_id=payload.customer_id,
        transactions_analyzed=len(payload.transactions),
        anomaly_count=len(anomalies),
        anomalies=[
            TransactionAnomalyResponse.model_validate(item) for item in anomalies
        ],
        message=message,
    )
    return APIResponse(success=True, message=message, data=data)


@router.get(
    "",
    response_model=APIResponse[list[TransactionAnomalyResponse]],
    summary="List transaction anomaly history",
)
async def list_transaction_anomalies(
    customer_id: UUID | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            resource_type="transaction_anomaly",
        )
    ),
) -> APIResponse[list[TransactionAnomalyResponse]]:
    service = AsyncTransactionAnomalyService(
        db, tenant_id=UUID(current_user["tenant_id"])
    )
    anomalies = await service.list_anomalies(customer_id=customer_id, limit=limit)
    return APIResponse(
        success=True,
        message="Transaction anomaly history retrieved successfully.",
        data=[TransactionAnomalyResponse.model_validate(item) for item in anomalies],
    )


@router.get(
    "/{anomaly_id}",
    response_model=APIResponse[TransactionAnomalyResponse],
    summary="Retrieve a transaction anomaly",
)
async def get_transaction_anomaly(
    anomaly_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            resource_type="transaction_anomaly",
        )
    ),
) -> APIResponse[TransactionAnomalyResponse]:
    anomaly = await AsyncTransactionAnomalyService(
        db, tenant_id=UUID(current_user["tenant_id"])
    ).get_anomaly(anomaly_id)
    return APIResponse(
        success=True,
        message="Transaction anomaly retrieved successfully.",
        data=TransactionAnomalyResponse.model_validate(anomaly),
    )
