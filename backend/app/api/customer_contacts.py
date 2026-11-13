from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.async_security import require_async_roles
from app.core.database import get_async_db
from app.core.responses import APIResponse
from app.schemas.customer_contact import (
    CustomerContactCreate,
    CustomerContactResponse,
    CustomerContactUpdate,
)
from app.services.async_customer_supporting_service import AsyncCustomerContactService
from app.utils.enums import UserRole

router = APIRouter(
    prefix="/api/v1/customers",
    tags=["Customer Contacts"],
)


@router.post(
    "/{customer_id}/contacts",
    response_model=APIResponse[CustomerContactResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create customer contact",
    description="Creates a new contact record for a customer.",
)
async def create_customer_contact(
    customer_id: UUID,
    contact_data: CustomerContactCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            resource_type="customer",
        )
    ),
) -> APIResponse[CustomerContactResponse]:
    service = AsyncCustomerContactService(db, UUID(current_user["tenant_id"]))

    contact = await service.create_contact(
        customer_id=customer_id,
        data=contact_data,
        created_by=UUID(current_user["sub"]),
    )

    return APIResponse(
        success=True,
        message="Customer contact created successfully.",
        data=CustomerContactResponse.model_validate(contact),
    )


@router.get(
    "/{customer_id}/contacts",
    response_model=APIResponse[list[CustomerContactResponse]],
    status_code=status.HTTP_200_OK,
    summary="Get customer contacts",
    description="Retrieves all contact records belonging to a customer.",
)
async def get_customer_contacts(
    customer_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            resource_type="customer",
        )
    ),
) -> APIResponse[list[CustomerContactResponse]]:
    service = AsyncCustomerContactService(db, UUID(current_user["tenant_id"]))

    contacts = await service.get_contacts(customer_id)

    return APIResponse(
        success=True,
        message="Customer contacts retrieved successfully.",
        data=[CustomerContactResponse.model_validate(contact) for contact in contacts],
    )


@router.put(
    "/{customer_id}/contacts/{contact_id}",
    response_model=APIResponse[CustomerContactResponse],
    status_code=status.HTTP_200_OK,
    summary="Update customer contact",
    description="Updates an existing customer contact record.",
)
async def update_customer_contact(
    customer_id: UUID,
    contact_id: UUID,
    contact_data: CustomerContactUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            resource_type="customer",
        )
    ),
) -> APIResponse[CustomerContactResponse]:
    service = AsyncCustomerContactService(db, UUID(current_user["tenant_id"]))

    contact = await service.update_contact(
        customer_id=customer_id,
        contact_id=contact_id,
        data=contact_data,
        updated_by=UUID(current_user["sub"]),
    )

    return APIResponse(
        success=True,
        message="Customer contact updated successfully.",
        data=CustomerContactResponse.model_validate(contact),
    )
