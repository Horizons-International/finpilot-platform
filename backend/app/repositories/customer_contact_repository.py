from uuid import UUID

from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.customer_contact import CustomerContact
from app.repositories.tenant_scoped_repository import TenantScopedRepository


class CustomerContactRepository(TenantScopedRepository[CustomerContact]):
    def __init__(self, db: Session, tenant_id: UUID | None = None) -> None:
        resolved_tenant_id = (
            tenant_id if tenant_id is not None else db.info.get("tenant_id")
        )
        if not isinstance(resolved_tenant_id, UUID):
            raise ValueError("A tenant context is required for customer contacts.")
        super().__init__(db, CustomerContact, resolved_tenant_id)

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
            raise ValueError("The customer does not belong to the current tenant.")

    def create(self, contact: CustomerContact) -> CustomerContact:
        self._ensure_customer_belongs_to_tenant(contact.customer_id)
        return super().create(contact)

    def update(self, contact: CustomerContact) -> CustomerContact:
        self._ensure_customer_belongs_to_tenant(contact.customer_id)
        return super().update(contact)

    def get_by_id(self, contact_id: UUID) -> CustomerContact | None:
        return self.query().filter(CustomerContact.id == contact_id).first()

    def get_by_customer_id(self, customer_id: UUID) -> list[CustomerContact]:
        self._ensure_customer_belongs_to_tenant(customer_id)
        return self.query().filter(CustomerContact.customer_id == customer_id).all()
