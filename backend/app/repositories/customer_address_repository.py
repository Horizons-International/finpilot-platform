from uuid import UUID

from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.customer_address import CustomerAddress
from app.repositories.tenant_scoped_repository import TenantScopedRepository
from app.utils.errors import not_found


class CustomerAddressRepository(TenantScopedRepository[CustomerAddress]):
    def __init__(self, db: Session, tenant_id: UUID | None = None) -> None:
        resolved_tenant_id = (
            tenant_id if tenant_id is not None else db.info.get("tenant_id")
        )
        if not isinstance(resolved_tenant_id, UUID):
            raise ValueError("A tenant context is required for customer addresses.")
        super().__init__(db, CustomerAddress, resolved_tenant_id)

    def _ensure_customer_belongs_to_tenant(self, customer_id: UUID) -> None:
        customer_exists = (
            self.db.query(Customer.id)
            .filter(
                Customer.id == customer_id,
                Customer.tenant_id == self.tenant_id,
            )
            .first()
        )
        if customer_exists is None:
            raise not_found("Customer")

    def create(self, address: CustomerAddress) -> CustomerAddress:
        self._ensure_customer_belongs_to_tenant(address.customer_id)
        return super().create(address)

    def update(self, address: CustomerAddress) -> CustomerAddress:
        self._ensure_customer_belongs_to_tenant(address.customer_id)
        return super().update(address)

    def get_by_id(self, address_id: UUID) -> CustomerAddress | None:
        return self.query().filter(CustomerAddress.id == address_id).first()

    def get_by_customer_id(self, customer_id: UUID) -> list[CustomerAddress]:
        self._ensure_customer_belongs_to_tenant(customer_id)
        return self.query().filter(CustomerAddress.customer_id == customer_id).all()

    def get_primary_by_customer_id(self, customer_id: UUID) -> CustomerAddress | None:
        self._ensure_customer_belongs_to_tenant(customer_id)
        return (
            self.query()
            .filter(
                CustomerAddress.customer_id == customer_id,
                CustomerAddress.is_primary.is_(True),
            )
            .first()
        )
