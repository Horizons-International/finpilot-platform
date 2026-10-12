from uuid import UUID

from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.document import CustomerDocument
from app.models.verification_case import IdentityVerificationCase
from app.repositories.tenant_scoped_repository import TenantScopedRepository


class CustomerDocumentRepository(TenantScopedRepository[CustomerDocument]):
    def __init__(self, db: Session, tenant_id: UUID | None = None) -> None:
        resolved_tenant_id = (
            tenant_id if tenant_id is not None else db.info.get("tenant_id")
        )
        if not isinstance(resolved_tenant_id, UUID):
            raise ValueError("A tenant context is required for customer documents.")
        super().__init__(db=db, model=CustomerDocument, tenant_id=resolved_tenant_id)

    def _validate_relationships(self, document: CustomerDocument) -> None:
        customer_exists = (
            self.db.query(Customer.id)
            .filter(
                Customer.id == document.customer_id,
                Customer.tenant_id == self.tenant_id,
            )
            .first()
        )
        if customer_exists is None:
            raise ValueError(
                "The document customer does not belong to the current tenant."
            )

        if document.verification_case_id is not None:
            case = (
                self.db.query(IdentityVerificationCase)
                .filter(
                    IdentityVerificationCase.id == document.verification_case_id,
                    IdentityVerificationCase.tenant_id == self.tenant_id,
                )
                .first()
            )
            if case is None or case.customer_id != document.customer_id:
                raise ValueError(
                    "The verification case must belong"
                    " to the current tenant and customer."
                )

    def create(self, document: CustomerDocument) -> CustomerDocument:
        self._validate_relationships(document)
        return super().create(document)

    def update(self, document: CustomerDocument) -> CustomerDocument:
        self._validate_relationships(document)
        return super().update(document)

    def get_by_id(self, document_id: UUID) -> CustomerDocument | None:
        return self.query().filter(CustomerDocument.id == document_id).first()

    def get_by_customer_id(self, customer_id: UUID) -> list[CustomerDocument]:
        return (
            self.query()
            .filter(CustomerDocument.customer_id == customer_id)
            .order_by(CustomerDocument.created_at.desc())
            .all()
        )

    def get_by_verification_case_id(
        self,
        verification_case_id: UUID,
    ) -> list[CustomerDocument]:
        return (
            self.query()
            .filter(CustomerDocument.verification_case_id == verification_case_id)
            .order_by(CustomerDocument.created_at.desc())
            .all()
        )

    def get_by_id_and_customer(
        self,
        document_id: UUID,
        customer_id: UUID,
    ) -> CustomerDocument | None:
        return (
            self.query()
            .filter(
                CustomerDocument.id == document_id,
                CustomerDocument.customer_id == customer_id,
            )
            .first()
        )

    def get_by_id_and_case(
        self,
        document_id: UUID,
        customer_id: UUID,
        verification_case_id: UUID,
    ) -> CustomerDocument | None:
        return (
            self.query()
            .filter(
                CustomerDocument.id == document_id,
                CustomerDocument.customer_id == customer_id,
                CustomerDocument.verification_case_id == verification_case_id,
            )
            .first()
        )
