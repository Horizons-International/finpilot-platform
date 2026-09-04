from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.responses import APIResponse
from app.core.security import require_roles
from app.schemas.customer_audit_log import (
    CustomerAuditLogListResponse,
    CustomerAuditLogResponse,
)
from app.services.customer_audit_log_service import CustomerAuditLogService
from app.services.customer_service import CustomerService
from app.utils.enums import UserRole

router = APIRouter(
    prefix="/api/v1/customers",
    tags=["Customer Audit History"],
)


@router.get(
    "/{customer_id}/audit-history",
    response_model=APIResponse[CustomerAuditLogListResponse],
    status_code=status.HTTP_200_OK,
    summary="Get customer audit history",
    description="Retrieve the field-level audit history for a customer.",
)
def get_customer_audit_history(
    customer_id: UUID,
    db: Session = Depends(get_db),
    _: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            resource_type="customer",
        ),
    ),
) -> APIResponse[CustomerAuditLogListResponse]:
    customer_service = CustomerService(db)

    customer_service.get_customer(customer_id)

    audit_service = CustomerAuditLogService(db)

    audit_logs = audit_service.get_customer_history(customer_id)

    response = CustomerAuditLogListResponse(
        audit_logs=[
            CustomerAuditLogResponse.model_validate(audit_log)
            for audit_log in audit_logs
        ],
    )

    return APIResponse(
        success=True,
        message="Customer audit history retrieved successfully.",
        data=response,
    )
