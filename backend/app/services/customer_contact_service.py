from uuid import UUID

from sqlalchemy.orm import Session

from app.models.customer_contact import CustomerContact
from app.repositories.customer_contact_repository import CustomerContactRepository
from app.schemas.customer_contact import (
    CustomerContactCreate,
    CustomerContactUpdate,
)
from app.utils.errors import not_found


class CustomerContactService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = CustomerContactRepository(db)

    def create_contact(
        self,
        customer_id: UUID,
        data: CustomerContactCreate,
    ) -> CustomerContact:
        contact = CustomerContact(
            customer_id=customer_id,
            phone_number=data.phone_number,
            email=data.email,
            preferred_contact_method=data.preferred_contact_method,
            phone_verified=data.phone_verified,
            email_verified=data.email_verified,
        )

        contact = self.repository.create(contact)
        self.db.commit()

        return contact

    def get_contacts(
        self,
        customer_id: UUID,
    ) -> list[CustomerContact]:
        return self.repository.get_by_customer_id(customer_id)

    def update_contact(
        self,
        customer_id: UUID,
        contact_id: UUID,
        data: CustomerContactUpdate,
    ) -> CustomerContact:
        contact = self.repository.get_by_id(contact_id)

        if contact is None or contact.customer_id != customer_id:
            raise not_found("Customer contact")

        update_data = data.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            setattr(contact, field, value)

        self.repository.update(contact)
        self.db.commit()

        return contact
