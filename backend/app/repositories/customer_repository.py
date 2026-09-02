from uuid import UUID

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.repositories.base_repository import BaseRepository
from app.utils.enums import CustomerStatus


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

    def search(
        self,
        customer_id: UUID | None = None,
        name: str | None = None,
        phone_number: str | None = None,
        email: str | None = None,
        status: CustomerStatus | None = None,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> tuple[list[Customer], int]:
        query = self.db.query(Customer)

        if customer_id is not None:
            query = query.filter(Customer.id == customer_id)

        if name:
            name_pattern = f"%{name}%"

            query = query.filter(
                or_(
                    Customer.first_name.ilike(name_pattern),
                    Customer.middle_name.ilike(name_pattern),
                    Customer.last_name.ilike(name_pattern),
                )
            )

        if phone_number:
            query = query.filter(Customer.phone_number.ilike(f"%{phone_number}%"))

        if email:
            query = query.filter(Customer.email.ilike(f"%{email}%"))

        if status is not None:
            query = query.filter(Customer.status == status)

        total = query.count()

        sortable_fields = {
            "created_at": Customer.created_at,
            "updated_at": Customer.updated_at,
            "first_name": Customer.first_name,
            "last_name": Customer.last_name,
            "email": Customer.email,
            "date_of_birth": Customer.date_of_birth,
        }

        sort_column = sortable_fields.get(sort_by)

        if sort_column is None:
            raise ValueError(
                f"Invalid sort field: {sort_by}",
            )

        if sort_order.lower() == "asc":
            query = query.order_by(sort_column.asc())
        else:
            query = query.order_by(sort_column.desc())

        # Pagination
        offset = (page - 1) * page_size

        customers = query.offset(offset).limit(page_size).all()

        return customers, total
