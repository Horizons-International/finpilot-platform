"""Tenant-scoped async persistence for customers."""

from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.repositories.async_tenant_scoped_repository import (
    AsyncTenantScopedRepository,
)
from app.utils.enums import CustomerStatus


class AsyncCustomerRepository(AsyncTenantScopedRepository[Customer]):
    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        super().__init__(db=db, model=Customer, tenant_id=tenant_id)

    async def get_by_id(self, customer_id: UUID) -> Customer | None:
        return await self.db.scalar(self.query().where(Customer.id == customer_id))

    async def get_by_email(self, email: str | None) -> Customer | None:
        return await self.db.scalar(self.query().where(Customer.email == email))

    async def search(
        self,
        *,
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
        statement = self.query()
        if customer_id is not None:
            statement = statement.where(Customer.id == customer_id)
        if name:
            pattern = f"%{name}%"
            statement = statement.where(
                or_(
                    Customer.first_name.ilike(pattern),
                    Customer.middle_name.ilike(pattern),
                    Customer.last_name.ilike(pattern),
                )
            )
        if phone_number:
            statement = statement.where(
                Customer.phone_number.ilike(f"%{phone_number}%")
            )
        if email:
            statement = statement.where(Customer.email.ilike(f"%{email}%"))
        if status is not None:
            statement = statement.where(Customer.status == status)

        total_statement = select(func.count()).select_from(statement.subquery())
        total = int(await self.db.scalar(total_statement) or 0)

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
            raise ValueError(f"Invalid sort field: {sort_by}")
        statement = statement.order_by(
            sort_column.asc() if sort_order.lower() == "asc" else sort_column.desc()
        )
        statement = statement.offset((page - 1) * page_size).limit(page_size)
        customers = list((await self.db.scalars(statement)).all())
        return customers, total
