from uuid import UUID

from sqlalchemy.orm import Session

from app.models.customer_address import CustomerAddress
from app.repositories.customer_address_repository import CustomerAddressRepository
from app.schemas.customer_address import (
    CustomerAddressCreate,
    CustomerAddressUpdate,
)
from app.utils.errors import not_found


class CustomerAddressService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = CustomerAddressRepository(db)

    def create_address(
        self,
        customer_id: UUID,
        data: CustomerAddressCreate,
    ) -> CustomerAddress:
        if data.is_primary:
            existing_primary = self.repository.get_primary_by_customer_id(customer_id)

            if existing_primary:
                existing_primary.is_primary = False
                self.repository.update(existing_primary)

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

        self.db.commit()

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
    ) -> CustomerAddress:
        address = self.repository.get_by_id(address_id)

        if address is None or address.customer_id != customer_id:
            raise not_found("Customer address")

        update_data = data.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            setattr(address, field, value)

        self.repository.update(address)

        self.db.commit()

        return address

    def set_primary(
        self,
        customer_id: UUID,
        address_id: UUID,
    ) -> CustomerAddress:
        address = self.repository.get_by_id(address_id)

        if address is None or address.customer_id != customer_id:
            raise not_found("Customer address")

        existing_primary = self.repository.get_primary_by_customer_id(customer_id)

        if existing_primary and existing_primary.id != address.id:
            existing_primary.is_primary = False
            self.repository.update(existing_primary)

        address.is_primary = True
        self.repository.update(address)

        self.db.commit()

        return address
