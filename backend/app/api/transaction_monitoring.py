from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_db
from app.core.responses import APIResponse
from app.core.security import require_roles
from app.schemas.transaction_monitoring import (
    TransactionMonitoringRequest,
    TransactionMonitoringResponse,
    TransactionMonitoringResultResponse,
)
from app.services.transaction_monitoring_service import (
    TransactionMonitoringService,
)
from app.utils.enums import TransactionMonitoringOutcome, UserRole
from app.utils.errors import unauthorized

router = APIRouter(
    prefix="/api/v1/transaction-monitoring",
    tags=["Transaction Monitoring"],
)


def _get_authenticated_user(
    current_user: dict[str, Any],
) -> tuple[UUID, str]:
    raw_user_id = current_user.get("sub")

    try:
        user_id = UUID(str(raw_user_id))
    except (TypeError, ValueError):
        raise unauthorized("Invalid authenticated user.")

    email = current_user["email"]

    if not isinstance(email, str) or not email:
        raise unauthorized("Authenticated user email is missing.")

    return user_id, email


def _request_metadata(
    request: Request,
) -> tuple[str | None, str | None]:
    client_host = request.client.host if request.client is not None else None

    user_agent = request.headers.get("user-agent")

    return client_host, user_agent


@router.post(
    "/evaluate",
    response_model=APIResponse[TransactionMonitoringResponse],
    status_code=status.HTTP_200_OK,
    summary="Evaluate a transaction",
    description=(
        "Evaluate a transaction against all active transaction "
        "AML rules and persist the monitoring results. "
        "Administrators and compliance officers can execute "
        "transaction monitoring."
    ),
)
def evaluate_transaction(
    payload: TransactionMonitoringRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            resource_type="transaction_monitoring",
        )
    ),
) -> APIResponse[TransactionMonitoringResponse]:
    user_id, email = _get_authenticated_user(current_user)

    ip_address, user_agent = _request_metadata(request)

    service = TransactionMonitoringService(db)

    persisted_results = service.monitor_transaction(
        payload=payload,
        user_id=user_id,
        email=email,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    response_results = [
        TransactionMonitoringResultResponse(
            id=result.id,
            transaction_id=result.transaction_id,
            customer_id=result.customer_id,
            rule_id=result.rule_id,
            result=result.result,
            alert_required=(result.result == TransactionMonitoringOutcome.MATCHED),
            created_at=result.created_at,
        )
        for result in persisted_results
    ]

    matched_count = sum(1 for result in response_results if result.alert_required)

    response = TransactionMonitoringResponse(
        transaction_id=payload.transaction_id,
        customer_id=payload.customer_id,
        evaluated_rule_count=len(response_results),
        matched_rule_count=matched_count,
        alerts_generated=matched_count,
        results=response_results,
    )

    return APIResponse(
        success=True,
        message="Transaction monitoring completed successfully.",
        data=response,
    )
