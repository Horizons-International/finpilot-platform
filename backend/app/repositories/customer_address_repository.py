from uuid import UUID

from sqlalchemy.orm import Session

from app.models.customer_address import CustomerAddress
from app.repositories.base_repository import BaseRepository


class CustomerAddressRepository(BaseRepository[CustomerAddress]):
    def __init__(self, db: Session) -> None:
        super().__init__(db, CustomerAddress)

    def get_by_id(
        self,
        address_id: UUID,
    ) -> CustomerAddress | None:
        return (
            self.db.query(CustomerAddress)
            .filter(CustomerAddress.id == address_id)
            .first()
        )

    def get_by_customer_id(
        self,
        customer_id: UUID,
    ) -> list[CustomerAddress]:
        return (
            self.db.query(CustomerAddress)
            .filter(CustomerAddress.customer_id == customer_id)
            .all()
        )

    def get_primary_by_customer_id(
        self,
        customer_id: UUID,
    ) -> CustomerAddress | None:
        return (
            self.db.query(CustomerAddress)
            .filter(
                CustomerAddress.customer_id == customer_id,
                CustomerAddress.is_primary.is_(True),
            )
            .first()
        )
