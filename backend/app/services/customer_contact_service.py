from uuid import UUID

from sqlalchemy.orm import Session

from app.models.customer_contact import CustomerContact
from app.repositories.customer_contact_repository import CustomerContactRepository
from app.schemas.customer_contact import (
    CustomerContactCreate,
    CustomerContactUpdate,
)
from app.services.customer_audit_log_service import CustomerAuditLogService
from app.utils.audit import serialize_audit_value
from app.utils.errors import not_found


class CustomerContactService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = CustomerContactRepository(db)
        self.customer_audit_service = CustomerAuditLogService(db)

    def create_contact(
        self,
        customer_id: UUID,
        data: CustomerContactCreate,
        created_by: UUID,
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

        self.customer_audit_service.create_audit_log(
            customer_id=customer_id,
            user_id=created_by,
            resource_type="contact",
            resource_id=contact.id,
            action="CREATE CONTACT",
            old_value=None,
            new_value={
                "phone_number": serialize_audit_value(contact.phone_number),
                "email": serialize_audit_value(contact.email),
                "preferred_contact_method": serialize_audit_value(
                    contact.preferred_contact_method
                ),
                "phone_verified": serialize_audit_value(contact.phone_verified),
                "email_verified": serialize_audit_value(contact.email_verified),
            },
        )

        self.db.commit()
        self.db.refresh(contact)

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
        updated_by: UUID,
    ) -> CustomerContact:
        contact = self.repository.get_by_id(contact_id)

        if contact is None or contact.customer_id != customer_id:
            raise not_found("Customer contact")

        update_data = data.model_dump(exclude_unset=True)

        if not update_data:
            return contact

        changed_fields: list[tuple[str, object | None, object | None]] = []

        for field, new_value in update_data.items():
            old_value = getattr(contact, field)

            if old_value == new_value:
                continue

            changed_fields.append(
                (
                    field,
                    old_value,
                    new_value,
                )
            )

        if not changed_fields:
            return contact

        for field, _, new_value in changed_fields:
            setattr(contact, field, new_value)

        contact = self.repository.update(contact)

        for field, old_value, new_value in changed_fields:
            self.customer_audit_service.create_audit_log(
                customer_id=customer_id,
                user_id=updated_by,
                resource_type="contact",
                resource_id=contact.id,
                action=f"UPDATE {field.replace('_', ' ').upper()}",
                old_value=serialize_audit_value(old_value),
                new_value=serialize_audit_value(new_value),
            )

        self.db.commit()
        self.db.refresh(contact)

        return contact
