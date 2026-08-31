from uuid import UUID

from app.models.customer import Customer
from app.repositories.base_repository import BaseRepository


class CustomerRepository(BaseRepository[Customer]):
    def get_by_id(self, customer_id: UUID) -> Customer | None: ...

    def get_by_email(self, email: str) -> Customer | None: ...
