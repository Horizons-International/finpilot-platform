from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.responses import APIResponse
from app.core.security import require_roles
from app.schemas.customer_address import (
    CustomerAddressCreate,
    CustomerAddressResponse,
    CustomerAddressUpdate,
)
from app.services.customer_address_service import CustomerAddressService
from app.utils.enums import UserRole

router = APIRouter(
    prefix="/api/v1/customers",
    tags=["Customer Addresses"],
)


@router.post(
    "/{customer_id}/addresses",
    response_model=APIResponse[CustomerAddressResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create customer address",
    description="Creates a new address for a customer.",
)
def create_customer_address(
    customer_id: UUID,
    data: CustomerAddressCreate,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            resource_type="customer",
        )
    ),
):
    service = CustomerAddressService(db)

    address = service.create_address(
        customer_id=customer_id,
        data=data,
        created_by=UUID(current_user["sub"]),
    )

    return APIResponse(
        success=True,
        message="Customer address created successfully.",
        data=CustomerAddressResponse.model_validate(address),
    )


@router.get(
    "/{customer_id}/addresses",
    response_model=APIResponse[list[CustomerAddressResponse]],
    summary="Get customer addresses",
    description="Retrieves all addresses belonging to a customer.",
)
def get_customer_addresses(
    customer_id: UUID,
    db: Session = Depends(get_db),
    _: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            resource_type="customer",
        )
    ),
):
    service = CustomerAddressService(db)

    addresses = service.get_addresses(
        customer_id=customer_id,
    )

    return APIResponse(
        success=True,
        message="Customer addresses retrieved successfully.",
        data=[CustomerAddressResponse.model_validate(address) for address in addresses],
    )


@router.put(
    "/{customer_id}/addresses/{address_id}",
    response_model=APIResponse[CustomerAddressResponse],
    summary="Update customer address",
    description="Updates an existing customer address.",
)
def update_customer_address(
    customer_id: UUID,
    address_id: UUID,
    data: CustomerAddressUpdate,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            resource_type="customer",
        )
    ),
):
    service = CustomerAddressService(db)

    address = service.update_address(
        customer_id=customer_id,
        address_id=address_id,
        data=data,
        updated_by=UUID(current_user["sub"]),
    )

    return APIResponse(
        success=True,
        message="Customer address updated successfully.",
        data=CustomerAddressResponse.model_validate(address),
    )


@router.patch(
    "/{customer_id}/addresses/{address_id}/primary",
    response_model=APIResponse[CustomerAddressResponse],
    summary="Mark address as primary",
    description="Marks a customer address as the primary address.",
)
def set_customer_address_primary(
    customer_id: UUID,
    address_id: UUID,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            resource_type="customer",
        )
    ),
):
    service = CustomerAddressService(db)

    address = service.set_primary(
        customer_id=customer_id,
        address_id=address_id,
        updated_by=UUID(current_user["sub"]),
    )

    return APIResponse(
        success=True,
        message="Customer address marked as primary successfully.",
        data=CustomerAddressResponse.model_validate(address),
    )
