"""Native-async partner endpoints authenticated with permission-scoped API keys."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api_key_security import APIKeyPrincipal
from app.core.async_api_key_security import require_async_api_key_permission
from app.core.database import get_async_db
from app.core.responses import APIResponse
from app.models.customer import Customer
from app.schemas.customer import CustomerResponse
from app.services.async_audit_service import AsyncAuditService
from app.utils.errors import not_found

router = APIRouter(prefix="/api/v1/integrations", tags=["Partner Integrations"])
CustomerReadKey = Annotated[
    APIKeyPrincipal, Depends(require_async_api_key_permission("customers:read"))
]


@router.get(
    "/customers",
    response_model=APIResponse[list[CustomerResponse]],
    summary="List customers with a partner API key",
)
async def list_partner_customers(
    principal: CustomerReadKey,
    limit: int = Query(default=100, ge=1, le=100),
    db: AsyncSession = Depends(get_async_db),
) -> APIResponse[list[CustomerResponse]]:
    rows = await db.scalars(
        select(Customer)
        .where(Customer.tenant_id == principal.tenant_id)
        .order_by(Customer.created_at.desc())
        .limit(limit)
    )
    customers = list(rows.all())
    await AsyncAuditService(db).record_data_access(
        user_id=None,
        entity_type="customer_collection",
        entity_id=None,
        access_type="READ",
        metadata={
            "actor_type": "API_KEY",
            "api_key_id": str(principal.api_key_id),
            "endpoint": "GET /api/v1/integrations/customers/",
        },
    )
    await db.commit()
    return APIResponse(
        success=True,
        message="Partner customers retrieved successfully.",
        data=[CustomerResponse.model_validate(row) for row in customers],
    )


@router.get(
    "/customers/{customer_id}",
    response_model=APIResponse[CustomerResponse],
    summary="Get one customer with a partner API key",
)
async def get_partner_customer(
    customer_id: UUID,
    principal: CustomerReadKey,
    response: Response,
    db: AsyncSession = Depends(get_async_db),
) -> APIResponse[CustomerResponse]:
    customer = await db.scalar(
        select(Customer).where(
            Customer.id == customer_id, Customer.tenant_id == principal.tenant_id
        )
    )
    if customer is None:
        response.status_code = 404
        raise not_found("Customer")
    await AsyncAuditService(db).record_data_access(
        user_id=None,
        entity_type="customer",
        entity_id=customer.id,
        access_type="READ",
        metadata={
            "actor_type": "API_KEY",
            "api_key_id": str(principal.api_key_id),
            "endpoint": "GET /api/v1/integrations/customers/{customer_id}",
        },
    )
    await db.commit()
    return APIResponse(
        success=True,
        message="Partner customer retrieved successfully.",
        data=CustomerResponse.model_validate(customer),
    )
