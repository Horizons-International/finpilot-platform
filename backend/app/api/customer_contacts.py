from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.responses import APIResponse
from app.core.security import Roles, require_roles
from app.schemas.customer_contact import (
    CustomerContactCreate,
    CustomerContactResponse,
    CustomerContactUpdate,
)
from app.services.customer_contact_service import CustomerContactService

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
def create_customer_contact(
    customer_id: UUID,
    data: CustomerContactCreate,
    db: Session = Depends(get_db),
    _: dict[str, Any] = Depends(require_roles(Roles.ADMINISTRATOR)),
) -> APIResponse[CustomerContactResponse]:
    service = CustomerContactService(db)

    contact = service.create_contact(
        customer_id,
        data,
    )

    return APIResponse(
        success=True,
        message="Customer contact created successfully.",
        data=CustomerContactResponse.model_validate(contact),
    )


@router.get(
    "/{customer_id}/contacts",
    response_model=APIResponse[list[CustomerContactResponse]],
    summary="Get customer contacts",
    description="Retrieves all contact records belonging to a customer.",
)
def get_customer_contacts(
    customer_id: UUID,
    db: Session = Depends(get_db),
    _: dict[str, Any] = Depends(require_roles(Roles.ADMINISTRATOR)),
) -> APIResponse[list[CustomerContactResponse]]:
    service = CustomerContactService(db)

    contacts = service.get_contacts(customer_id)

    return APIResponse(
        success=True,
        message="Customer contacts retrieved successfully.",
        data=[CustomerContactResponse.model_validate(contact) for contact in contacts],
    )


@router.put(
    "/{customer_id}/contacts/{contact_id}",
    response_model=APIResponse[CustomerContactResponse],
    summary="Update customer contact",
    description="Updates an existing customer contact record.",
)
def update_customer_contact(
    customer_id: UUID,
    contact_id: UUID,
    data: CustomerContactUpdate,
    db: Session = Depends(get_db),
    _: dict[str, Any] = Depends(require_roles(Roles.ADMINISTRATOR)),
) -> APIResponse[CustomerContactResponse]:
    service = CustomerContactService(db)

    contact = service.update_contact(
        customer_id,
        contact_id,
        data,
    )

    return APIResponse(
        success=True,
        message="Customer contact updated successfully.",
        data=CustomerContactResponse.model_validate(contact),
    )
