from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.async_security import require_async_roles
from app.core.database import get_async_db
from app.core.responses import APIResponse
from app.schemas.customer_audit_log import (
    CustomerAuditLogListResponse,
    CustomerAuditLogResponse,
)
from app.services.async_customer_supporting_service import AsyncCustomerAuditLogService
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
async def get_customer_audit_history(
    customer_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            resource_type="customer",
        ),
    ),
) -> APIResponse[CustomerAuditLogListResponse]:
    audit_service = AsyncCustomerAuditLogService(db, UUID(current_user["tenant_id"]))
    audit_logs = await audit_service.get_customer_history(customer_id)

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
