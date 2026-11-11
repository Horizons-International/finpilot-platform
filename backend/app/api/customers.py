from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import EmailStr

from app.core.async_dependencies import get_async_customer_service
from app.core.async_security import require_async_roles
from app.core.responses import APIResponse
from app.schemas.customer import (
    CustomerCreate,
    CustomerListResponse,
    CustomerResponse,
    CustomerSortField,
    CustomerStatusUpdate,
    CustomerUpdate,
)
from app.services.async_customer_service import AsyncCustomerService
from app.utils.constants import DEFAULT_PAGE, DEFAULT_PAGE_SIZE
from app.utils.enums import CustomerStatus, UserRole

router = APIRouter(prefix="/api/v1/customers", tags=["Customers"])


@router.post(
    "",
    response_model=APIResponse[CustomerResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create customer",
    description="Creates a new customer.",
)
async def create_customer(
    request: Request,
    customer_data: CustomerCreate,
    service: AsyncCustomerService = Depends(get_async_customer_service),
    current_user: dict[str, Any] = Depends(
        require_async_roles(UserRole.ADMINISTRATOR, resource_type="customer")
    ),
) -> APIResponse[CustomerResponse]:
    customer = await service.create_customer(
        customer_data=customer_data,
        created_by=UUID(current_user["sub"]),
        email=current_user["email"],
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return APIResponse(
        success=True,
        message="Customer created successfully.",
        data=CustomerResponse.model_validate(customer),
    )


@router.put(
    "/{customer_id}",
    response_model=APIResponse[CustomerResponse],
    status_code=status.HTTP_200_OK,
    summary="Update customer",
    description="Updates an existing customer.",
)
async def update_customer(
    request: Request,
    customer_id: UUID,
    customer_data: CustomerUpdate,
    service: AsyncCustomerService = Depends(get_async_customer_service),
    current_user: dict[str, Any] = Depends(
        require_async_roles(UserRole.ADMINISTRATOR, resource_type="customer")
    ),
) -> APIResponse[CustomerResponse]:
    customer = await service.update_customer(
        customer_id=customer_id,
        customer_data=customer_data,
        updated_by=UUID(current_user["sub"]),
        email=current_user["email"],
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return APIResponse(
        success=True,
        message="Customer updated successfully.",
        data=CustomerResponse.model_validate(customer),
    )


@router.patch(
    "/{customer_id}/status",
    response_model=APIResponse[CustomerResponse],
    status_code=status.HTTP_200_OK,
    summary="Change customer status",
    description="Changes the status of an existing customer.",
)
async def update_customer_status(
    request: Request,
    customer_id: UUID,
    status_data: CustomerStatusUpdate,
    service: AsyncCustomerService = Depends(get_async_customer_service),
    current_user: dict[str, Any] = Depends(
        require_async_roles(UserRole.ADMINISTRATOR, resource_type="customer")
    ),
) -> APIResponse[CustomerResponse]:
    customer = await service.update_status(
        customer_id=customer_id,
        new_status=status_data.status,
        changed_by=UUID(current_user["sub"]),
        email=current_user["email"],
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return APIResponse(
        success=True,
        message="Customer status updated successfully.",
        data=CustomerResponse.model_validate(customer),
    )


@router.get(
    "",
    response_model=APIResponse[CustomerListResponse],
    status_code=status.HTTP_200_OK,
    summary="Search customers",
    description=(
        "Searches customers by ID, name, phone number, or email "
        "with pagination, filtering, and sorting."
    ),
)
async def search_customers(
    customer_id: UUID | None = Query(
        default=None, description="Filter by customer ID."
    ),
    name: str | None = Query(
        default=None, description="Search by first, middle, or last name."
    ),
    phone_number: str | None = Query(
        default=None, description="Search by phone number."
    ),
    email: EmailStr | None = Query(
        default=None, description="Filter by email address."
    ),
    status: CustomerStatus | None = Query(default=None),
    page: int = Query(default=DEFAULT_PAGE),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE),
    sort_by: str = Query(default=CustomerSortField.CREATED_AT),
    sort_order: str = Query(default="desc", pattern="^(asc|desc)$"),
    service: AsyncCustomerService = Depends(get_async_customer_service),
    _: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            resource_type="customer",
        )
    ),
) -> APIResponse[CustomerListResponse]:
    result = await service.search_customers(
        customer_id=customer_id,
        name=name,
        phone_number=phone_number,
        email=str(email) if email is not None else None,
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
    status_code=status.HTTP_200_OK,
    summary="Get customer",
    description="Retrieves a customer by ID.",
)
async def get_customer(
    customer_id: UUID,
    service: AsyncCustomerService = Depends(get_async_customer_service),
    _: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            resource_type="customer",
        )
    ),
) -> APIResponse[CustomerResponse]:
    customer = await service.get_customer(customer_id)
    return APIResponse(
        success=True,
        message="Customer retrieved successfully.",
        data=CustomerResponse.model_validate(customer),
    )
