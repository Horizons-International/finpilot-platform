from uuid import UUID

from sqlalchemy.orm import Session

from app.models.customer_address import CustomerAddress
from app.repositories.customer_address_repository import CustomerAddressRepository
from app.schemas.customer_address import (
    CustomerAddressCreate,
    CustomerAddressUpdate,
)
from app.services.customer_audit_log_service import CustomerAuditLogService
from app.utils.audit import serialize_audit_value
from app.utils.errors import not_found


class CustomerAddressService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = CustomerAddressRepository(db)
        self.customer_audit_service = CustomerAuditLogService(db)

    def create_address(
        self,
        customer_id: UUID,
        data: CustomerAddressCreate,
        created_by: UUID,
    ) -> CustomerAddress:
        previous_primary: CustomerAddress | None = None

        if data.is_primary:
            previous_primary = self.repository.get_primary_by_customer_id(customer_id)

            if previous_primary:
                previous_primary.is_primary = False
                self.repository.update(previous_primary)

                self.customer_audit_service.create_audit_log(
                    customer_id=customer_id,
                    user_id=created_by,
                    resource_type="address",
                    resource_id=previous_primary.id,
                    action="UPDATE PRIMARY STATUS",
                    old_value=True,
                    new_value=False,
                )

        address = CustomerAddress(
            customer_id=customer_id,
            address_line_1=data.address_line_1,
            address_line_2=data.address_line_2,
            city=data.city,
            state=data.state,
            country=data.country,
            postal_code=data.postal_code,
            address_type=data.address_type,
            is_primary=data.is_primary,
        )

        address = self.repository.create(address)

        self.customer_audit_service.create_audit_log(
            customer_id=customer_id,
            user_id=created_by,
            resource_type="address",
            resource_id=address.id,
            action="CREATE ADDRESS",
            old_value=None,
            new_value={
                "address_line_1": serialize_audit_value(address.address_line_1),
                "address_line_2": serialize_audit_value(address.address_line_2),
                "city": serialize_audit_value(address.city),
                "state": serialize_audit_value(address.state),
                "country": serialize_audit_value(address.country),
                "postal_code": serialize_audit_value(address.postal_code),
                "address_type": serialize_audit_value(address.address_type),
                "is_primary": serialize_audit_value(address.is_primary),
            },
        )

        self.db.commit()
        self.db.refresh(address)

        return address

    def get_addresses(
        self,
        customer_id: UUID,
    ) -> list[CustomerAddress]:
        return self.repository.get_by_customer_id(customer_id)

    def update_address(
        self,
        customer_id: UUID,
        address_id: UUID,
        data: CustomerAddressUpdate,
        updated_by: UUID,
    ) -> CustomerAddress:
        address = self.repository.get_by_id(address_id)

        if address is None or address.customer_id != customer_id:
            raise not_found("Customer address")

        update_data = data.model_dump(exclude_unset=True)

        # Empty request: nothing to update.
        if not update_data:
            return address

        changed_fields: list[tuple[str, object | None, object | None]] = []

        for field, new_value in update_data.items():
            old_value = getattr(address, field)

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
            return address

        # If the address is being changed to primary,
        # demote the current primary address first
        if update_data.get("is_primary") is True and not address.is_primary:
            existing_primary = self.repository.get_primary_by_customer_id(customer_id)

            if existing_primary and existing_primary.id != address.id:
                old_primary_value = existing_primary.is_primary

                existing_primary.is_primary = False
                self.repository.update(existing_primary)

                self.customer_audit_service.create_audit_log(
                    customer_id=customer_id,
                    user_id=updated_by,
                    resource_type="address",
                    resource_id=existing_primary.id,
                    action="UPDATE PRIMARY STATUS",
                    old_value=old_primary_value,
                    new_value=False,
                )

        for field, _, new_value in changed_fields:
            setattr(address, field, new_value)

        address = self.repository.update(address)

        for field, old_value, new_value in changed_fields:
            self.customer_audit_service.create_audit_log(
                customer_id=customer_id,
                user_id=updated_by,
                resource_type="address",
                resource_id=address.id,
                action=f"UPDATE {field.replace('_', ' ').upper()}",
                old_value=serialize_audit_value(old_value),
                new_value=serialize_audit_value(new_value),
            )

        self.db.commit()
        self.db.refresh(address)

        return address

    def set_primary(
        self,
        customer_id: UUID,
        address_id: UUID,
        updated_by: UUID,
    ) -> CustomerAddress:
        address = self.repository.get_by_id(address_id)

        if address is None or address.customer_id != customer_id:
            raise not_found("Customer address")

        # Nothing changed.
        if address.is_primary:
            return address

        existing_primary = self.repository.get_primary_by_customer_id(customer_id)

        if existing_primary and existing_primary.id != address.id:
            existing_primary.is_primary = False
            self.repository.update(existing_primary)

            self.customer_audit_service.create_audit_log(
                customer_id=customer_id,
                user_id=updated_by,
                resource_type="address",
                resource_id=existing_primary.id,
                action="UPDATE PRIMARY STATUS",
                old_value=True,
                new_value=False,
            )

        address.is_primary = True
        self.repository.update(address)

        self.customer_audit_service.create_audit_log(
            customer_id=customer_id,
            user_id=updated_by,
            resource_type="address",
            resource_id=address.id,
            action="SET PRIMARY ADDRESS",
            old_value=False,
            new_value=True,
        )

        self.db.commit()
        self.db.refresh(address)

        return address
