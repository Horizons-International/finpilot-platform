from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.document import CustomerDocument
from app.models.verification_case import IdentityVerificationCase
from app.repositories.async_tenant_scoped_repository import (
    AsyncTenantScopedRepository,
    resolve_async_tenant_id,
)


class AsyncCustomerDocumentRepository(AsyncTenantScopedRepository[CustomerDocument]):
    def __init__(self, db: AsyncSession, tenant_id: UUID | None = None) -> None:
        resolved_tenant_id = resolve_async_tenant_id(db, tenant_id)
        assert resolved_tenant_id is not None
        super().__init__(
            db=db,
            model=CustomerDocument,
            tenant_id=resolved_tenant_id,
        )

    async def _validate_relationships(self, document: CustomerDocument) -> None:
        customer_id = await self.db.scalar(
            select(Customer.id).where(
                Customer.id == document.customer_id,
                Customer.tenant_id == self.tenant_id,
            )
        )
        if customer_id is None:
            raise ValueError(
                "The document customer does not belong to the current tenant."
            )

        if document.verification_case_id is not None:
            case = await self.db.scalar(
                select(IdentityVerificationCase).where(
                    IdentityVerificationCase.id == document.verification_case_id,
                    IdentityVerificationCase.tenant_id == self.tenant_id,
                )
            )
            if case is None or case.customer_id != document.customer_id:
                raise ValueError(
                    "The verification case must belong"
                    " to the current tenant and customer."
                )

    async def create(self, document: CustomerDocument) -> CustomerDocument:
        await self._validate_relationships(document)
        return await super().create(document)

    async def update(self, document: CustomerDocument) -> CustomerDocument:
        await self._validate_relationships(document)
        return await super().update(document)

    async def get_by_id(self, document_id: UUID) -> CustomerDocument | None:
        return await self.db.scalar(
            self.query().where(CustomerDocument.id == document_id)
        )

    async def get_by_customer_id(self, customer_id: UUID) -> list[CustomerDocument]:
        statement = (
            self.query()
            .where(CustomerDocument.customer_id == customer_id)
            .order_by(CustomerDocument.created_at.desc())
        )
        result = await self.db.scalars(statement)
        return list(result.all())

    async def get_by_verification_case_id(
        self,
        verification_case_id: UUID,
    ) -> list[CustomerDocument]:
        statement = (
            self.query()
            .where(CustomerDocument.verification_case_id == verification_case_id)
            .order_by(CustomerDocument.created_at.desc())
        )
        result = await self.db.scalars(statement)
        return list(result.all())

    async def get_by_id_and_customer(
        self,
        document_id: UUID,
        customer_id: UUID,
    ) -> CustomerDocument | None:
        statement = self.query().where(
            CustomerDocument.id == document_id,
            CustomerDocument.customer_id == customer_id,
        )
        return await self.db.scalar(statement)

    async def get_by_id_and_case(
        self,
        document_id: UUID,
        customer_id: UUID,
        verification_case_id: UUID,
    ) -> CustomerDocument | None:
        statement = self.query().where(
            CustomerDocument.id == document_id,
            CustomerDocument.customer_id == customer_id,
            CustomerDocument.verification_case_id == verification_case_id,
        )
        return await self.db.scalar(statement)
