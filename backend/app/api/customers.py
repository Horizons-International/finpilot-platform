from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.responses import APIResponse
from app.core.security import Roles, require_roles
from app.schemas.customer import (
    CustomerCreate,
    CustomerResponse,
    CustomerUpdate,
)
from app.services.customer_service import CustomerService

router = APIRouter(
    prefix="/api/v1/customers",
    tags=["Customers"],
)


@router.post(
    "",
    response_model=APIResponse[CustomerResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create customer",
    description="Creates a new customer.",
)
def create_customer(
    customer_data: CustomerCreate,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(require_roles(Roles.ADMINISTRATOR)),
):
    service = CustomerService(db)

    customer = service.create_customer(
        customer_data=customer_data,
        user_id=UUID(current_user["sub"]),
    )

    return APIResponse(
        success=True,
        message="Customer created successfully.",
        data=CustomerResponse.model_validate(customer),
    )


@router.get(
    "/{customer_id}",
    response_model=APIResponse[CustomerResponse],
    summary="Get customer",
    description="Retrieves a customer by ID.",
)
def get_customer(
    customer_id: UUID,
    db: Session = Depends(get_db),
    _: dict[str, Any] = Depends(require_roles(Roles.ADMINISTRATOR)),
):
    service = CustomerService(db)

    customer = service.get_customer(
        customer_id=customer_id,
    )

    return APIResponse(
        success=True,
        message="Customer retrieved successfully.",
        data=CustomerResponse.model_validate(customer),
    )


@router.put(
    "/{customer_id}",
    response_model=APIResponse[CustomerResponse],
    summary="Update customer",
    description="Updates an existing customer.",
)
def update_customer(
    customer_id: UUID,
    customer_data: CustomerUpdate,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(require_roles(Roles.ADMINISTRATOR)),
):
    service = CustomerService(db)

    customer = service.update_customer(
        customer_id=customer_id,
        customer_data=customer_data,
        user_id=UUID(current_user["sub"]),
    )

    return APIResponse(
        success=True,
        message="Customer updated successfully.",
        data=CustomerResponse.model_validate(customer),
    )
