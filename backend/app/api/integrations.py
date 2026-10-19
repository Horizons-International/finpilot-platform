from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.api_key_security import APIKeyPrincipal, require_api_key_permission
from app.core.database import get_db
from app.core.responses import APIResponse
from app.models.customer import Customer
from app.schemas.customer import CustomerResponse
from app.services.audit_event_service import AuditEventService
from app.utils.errors import not_found

router = APIRouter(
    prefix="/api/v1/integrations",
    tags=["Partner Integrations"],
)

CustomerReadKey = Annotated[
    APIKeyPrincipal,
    Depends(require_api_key_permission("customers:read")),
]


@router.get(
    "/customers",
    response_model=APIResponse[list[CustomerResponse]],
    summary="List customers with a partner API key",
    description=(
        "Requires an X-API-Key header with the customers:read permission. "
        "Results are limited to the API key's tenant."
    ),
)
def list_partner_customers(
    principal: CustomerReadKey,
    limit: int = Query(default=100, ge=1, le=100),
    db: Session = Depends(get_db),
) -> APIResponse[list[CustomerResponse]]:
    customers = list(
        db.scalars(
            select(Customer)
            .where(Customer.tenant_id == principal.tenant_id)
            .order_by(Customer.created_at.desc())
            .limit(limit)
        ).all()
    )

    AuditEventService(db, principal.tenant_id).record_event(
        action="DATA_ACCESS",
        user_id=None,
        entity_type="customer_collection",
        entity_id=None,
        metadata={
            "access_type": "READ",
            "actor_type": "API_KEY",
            "api_key_id": str(principal.api_key_id),
            "endpoint": "GET /api/v1/integrations/customers/",
        },
    )

    db.commit()

    return APIResponse(
        success=True,
        message="Partner customers retrieved successfully.",
        data=[CustomerResponse.model_validate(customer) for customer in customers],
    )


@router.get(
    "/customers/{customer_id}",
    response_model=APIResponse[CustomerResponse],
    summary="Get one customer with a partner API key",
)
def get_partner_customer(
    customer_id: UUID,
    principal: CustomerReadKey,
    response: Response,
    db: Session = Depends(get_db),
) -> APIResponse[CustomerResponse]:
    customer = db.scalar(
        select(Customer).where(
            Customer.id == customer_id,
            Customer.tenant_id == principal.tenant_id,
        )
    )
    if customer is None:
        response.status_code = 404
        raise not_found("Customer")

    AuditEventService(db, principal.tenant_id).record_event(
        action="DATA_ACCESS",
        user_id=None,
        entity_type="customer",
        entity_id=customer.id,
        metadata={
            "access_type": "READ",
            "actor_type": "API_KEY",
            "api_key_id": str(principal.api_key_id),
            "endpoint": "GET /api/v1/integrations/customers/{customer_id}",
        },
    )

    db.commit()

    return APIResponse(
        success=True,
        message="Partner customer retrieved successfully.",
        data=CustomerResponse.model_validate(customer),
    )
