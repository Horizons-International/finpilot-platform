from uuid import UUID

from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.repositories.base_repository import BaseRepository


class CustomerRepository(BaseRepository[Customer]):
    def __init__(self, db: Session) -> None:
        super().__init__(db, Customer)

    def get_by_id(self, customer_id: UUID) -> Customer | None:
        return (
            self.db.query(Customer)
            .filter(
                Customer.id == customer_id,
            )
            .first()
        )

    def get_by_email(self, email: str | None) -> Customer | None:
        return (
            self.db.query(Customer)
            .filter(
                Customer.email == email,
            )
            .first()
        )
