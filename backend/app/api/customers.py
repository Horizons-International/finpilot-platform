from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import EmailStr
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.responses import APIResponse
from app.core.security import Roles, require_roles
from app.models.customer import CustomerStatus
from app.schemas.customer import (
    CustomerCreate,
    CustomerListResponse,
    CustomerResponse,
    CustomerSortField,
    CustomerStatusUpdate,
    CustomerUpdate,
)
from app.services.customer_service import CustomerService
from app.utils.constants import DEFAULT_PAGE, DEFAULT_PAGE_SIZE

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
        created_by=UUID(current_user["sub"]),
    )

    return APIResponse(
        success=True,
        message="Customer created successfully.",
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
        updated_by=UUID(current_user["sub"]),
    )

    return APIResponse(
        success=True,
        message="Customer updated successfully.",
        data=CustomerResponse.model_validate(customer),
    )


@router.patch(
    "/{customer_id}/status",
    response_model=APIResponse[CustomerResponse],
)
def update_customer_status(
    customer_id: UUID,
    status_data: CustomerStatusUpdate,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(
            Roles.ADMINISTRATOR,
        )
    ),
):
    service = CustomerService(db)

    customer = service.update_status(
        customer_id=customer_id,
        new_status=status_data.status,
        changed_by=UUID(current_user["sub"]),
    )

    return APIResponse(
        success=True,
        message="Customer status updated successfully.",
        data=CustomerResponse.model_validate(customer),
    )


@router.get(
    "",
    response_model=APIResponse[CustomerListResponse],
    summary="Search customers",
    description=(
        "Searches customers by ID, name, phone number, or email "
        "with pagination, filtering, and sorting."
    ),
)
def search_customers(
    customer_id: UUID | None = Query(
        default=None,
        description="Filter by customer ID.",
    ),
    name: str | None = Query(
        default=None,
        description="Search by first, middle, or last name.",
    ),
    phone_number: str | None = Query(
        default=None,
        description="Search by phone number.",
    ),
    email: EmailStr | None = Query(
        default=None,
        description="Filter by email address.",
    ),
    status: CustomerStatus | None = Query(
        default=None,
        description="Filter by customer status.",
    ),
    page: int = Query(
        default=DEFAULT_PAGE,
    ),
    page_size: int = Query(
        default=DEFAULT_PAGE_SIZE,
    ),
    sort_by: str = Query(
        default=CustomerSortField.CREATED_AT,
    ),
    sort_order: str = Query(
        default="desc",
        pattern="^(asc|desc)$",
    ),
    db: Session = Depends(get_db),
    _: dict[str, Any] = Depends(
        require_roles(
            Roles.ADMINISTRATOR,
        )
    ),
):
    service = CustomerService(db)

    result = service.search_customers(
        customer_id=customer_id,
        name=name,
        phone_number=phone_number,
        email=email,
        status=status,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
    )

    return APIResponse(
        success=True,
        message="Customers retrieved successfully.",
        data=result,
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
