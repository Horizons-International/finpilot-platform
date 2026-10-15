"""Tenant-scoped transaction-anomaly analysis and history endpoints."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.responses import APIResponse
from app.core.security import require_roles
from app.schemas.transaction_anomaly import (
    TransactionAnomalyAnalysisRequest,
    TransactionAnomalyAnalysisResponse,
    TransactionAnomalyResponse,
)
from app.services.transaction_anomaly_service import TransactionAnomalyService
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
        "historical activity. Findings are "
        "investigative signals, not proof of wrongdoing."
    ),
)
def analyze_transaction_anomalies(
    payload: TransactionAnomalyAnalysisRequest,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            resource_type="transaction_anomaly",
        )
    ),
) -> APIResponse[TransactionAnomalyAnalysisResponse]:
    service = TransactionAnomalyService(
        db,
        tenant_id=UUID(current_user["tenant_id"]),
    )
    anomalies, message = service.analyze(payload)
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
def list_transaction_anomalies(
    customer_id: UUID | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            resource_type="transaction_anomaly",
        )
    ),
) -> APIResponse[list[TransactionAnomalyResponse]]:
    service = TransactionAnomalyService(db, tenant_id=UUID(current_user["tenant_id"]))
    anomalies = service.list_anomalies(customer_id=customer_id, limit=limit)
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
def get_transaction_anomaly(
    anomaly_id: UUID,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            resource_type="transaction_anomaly",
        )
    ),
) -> APIResponse[TransactionAnomalyResponse]:
    anomaly = TransactionAnomalyService(
        db, tenant_id=UUID(current_user["tenant_id"])
    ).get_anomaly(anomaly_id)
    return APIResponse(
        success=True,
        message="Transaction anomaly retrieved successfully.",
        data=TransactionAnomalyResponse.model_validate(anomaly),
    )
