from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.async_security import require_async_roles
from app.core.database import get_async_db
from app.core.responses import APIResponse
from app.schemas.customer_address import (
    CustomerAddressCreate,
    CustomerAddressResponse,
    CustomerAddressUpdate,
)
from app.services.async_customer_supporting_service import AsyncCustomerAddressService
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
async def create_customer_address(
    customer_id: UUID,
    data: CustomerAddressCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            resource_type="customer",
        )
    ),
) -> APIResponse[CustomerAddressResponse]:
    service = AsyncCustomerAddressService(db, UUID(current_user["tenant_id"]))

    address = await service.create_address(
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
    status_code=status.HTTP_200_OK,
    summary="Get customer addresses",
    description="Retrieves all addresses belonging to a customer.",
)
async def get_customer_addresses(
    customer_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            resource_type="customer",
        )
    ),
) -> APIResponse[list[CustomerAddressResponse]]:
    service = AsyncCustomerAddressService(db, UUID(current_user["tenant_id"]))

    addresses = await service.get_addresses(customer_id=customer_id)

    return APIResponse(
        success=True,
        message="Customer addresses retrieved successfully.",
        data=[CustomerAddressResponse.model_validate(address) for address in addresses],
    )


@router.put(
    "/{customer_id}/addresses/{address_id}",
    response_model=APIResponse[CustomerAddressResponse],
    status_code=status.HTTP_200_OK,
    summary="Update customer address",
    description="Updates an existing customer address.",
)
async def update_customer_address(
    customer_id: UUID,
    address_id: UUID,
    data: CustomerAddressUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            resource_type="customer",
        )
    ),
) -> APIResponse[CustomerAddressResponse]:
    service = AsyncCustomerAddressService(db, UUID(current_user["tenant_id"]))

    address = await service.update_address(
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
    status_code=status.HTTP_200_OK,
    summary="Mark address as primary",
    description="Marks a customer address as the primary address.",
)
async def set_customer_address_primary(
    customer_id: UUID,
    address_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            resource_type="customer",
        )
    ),
) -> APIResponse[CustomerAddressResponse]:
    service = AsyncCustomerAddressService(db, UUID(current_user["tenant_id"]))

    address = await service.set_primary(
        customer_id=customer_id,
        address_id=address_id,
        updated_by=UUID(current_user["sub"]),
    )

    return APIResponse(
        success=True,
        message="Customer address marked as primary successfully.",
        data=CustomerAddressResponse.model_validate(address),
    )
