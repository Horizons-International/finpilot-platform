from uuid import UUID

from sqlalchemy.orm import Session

from app.models.customer_contact import CustomerContact
from app.repositories.base_repository import BaseRepository


class CustomerContactRepository(BaseRepository[CustomerContact]):
    def __init__(self, db: Session) -> None:
        super().__init__(db, CustomerContact)

    def get_by_id(self, contact_id: UUID) -> CustomerContact | None:
        return (
            self.db.query(CustomerContact)
            .filter(CustomerContact.id == contact_id)
            .first()
        )

    def get_by_customer_id(self, customer_id: UUID) -> list[CustomerContact]:
        return (
            self.db.query(CustomerContact)
            .filter(CustomerContact.customer_id == customer_id)
            .all()
        )
