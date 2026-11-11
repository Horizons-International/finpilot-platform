"""Tenant-scoped async persistence for compliance cases and history."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.compliance_case import ComplianceCase
from app.models.compliance_case_history import ComplianceCaseHistory
from app.models.customer import Customer
from app.models.user import User
from app.repositories.async_tenant_scoped_repository import (
    AsyncTenantScopedRepository,
)
from app.utils.enums import ComplianceCaseStatus, ComplianceCaseType


class AsyncComplianceCaseRepository(AsyncTenantScopedRepository[ComplianceCase]):
    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        super().__init__(db=db, model=ComplianceCase, tenant_id=tenant_id)

    async def _validate_related_ownership(self, case: ComplianceCase) -> None:
        customer_exists = await self.db.scalar(
            select(Customer.id).where(
                Customer.id == case.customer_id,
                Customer.tenant_id == self.tenant_id,
            )
        )
        if customer_exists is None:
            raise ValueError("The customer does not belong to the current tenant.")
        if case.assigned_to is not None:
            user_exists = await self.db.scalar(
                select(User.id).where(
                    User.id == case.assigned_to,
                    User.tenant_id == self.tenant_id,
                )
            )
            if user_exists is None:
                raise ValueError(
                    "The assigned user does not belong to the current tenant."
                )

    async def create(self, entity: ComplianceCase) -> ComplianceCase:
        await self._validate_related_ownership(entity)
        return await super().create(entity)

    async def update(self, entity: ComplianceCase) -> ComplianceCase:
        if entity.tenant_id != self.tenant_id:
            raise ValueError("Cannot update a compliance case owned by another tenant.")
        await self._validate_related_ownership(entity)
        return await super().update(entity)

    async def get_by_id(self, case_id: UUID) -> ComplianceCase | None:
        return await self.db.scalar(self.query().where(ComplianceCase.id == case_id))

    async def get_by_customer_id(self, customer_id: UUID) -> list[ComplianceCase]:
        statement = (
            self.query()
            .where(ComplianceCase.customer_id == customer_id)
            .order_by(ComplianceCase.created_at.desc())
        )
        return list((await self.db.scalars(statement)).all())

    async def get_all(
        self,
        *,
        status: ComplianceCaseStatus | None = None,
        case_type: ComplianceCaseType | None = None,
        assigned_to: UUID | None = None,
    ) -> list[ComplianceCase]:
        statement = self.query()
        if status is not None:
            statement = statement.where(ComplianceCase.status == status)
        if case_type is not None:
            statement = statement.where(ComplianceCase.case_type == case_type)
        if assigned_to is not None:
            statement = statement.where(ComplianceCase.assigned_to == assigned_to)
        statement = statement.order_by(ComplianceCase.created_at.desc())
        return list((await self.db.scalars(statement)).all())


class AsyncComplianceCaseHistoryRepository(
    AsyncTenantScopedRepository[ComplianceCaseHistory]
):
    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        super().__init__(db=db, model=ComplianceCaseHistory, tenant_id=tenant_id)

    async def create(self, entity: ComplianceCaseHistory) -> ComplianceCaseHistory:
        case_exists = await self.db.scalar(
            select(ComplianceCase.id).where(
                ComplianceCase.id == entity.compliance_case_id,
                ComplianceCase.tenant_id == self.tenant_id,
            )
        )
        if case_exists is None:
            raise ValueError("The compliance case does not belong to this tenant.")
        user_exists = await self.db.scalar(
            select(User.id).where(
                User.id == entity.changed_by,
                User.tenant_id == self.tenant_id,
            )
        )
        if user_exists is None:
            raise ValueError("The user does not belong to this tenant.")
        return await super().create(entity)

    async def get_by_case_id(
        self, compliance_case_id: UUID
    ) -> list[ComplianceCaseHistory]:
        statement = (
            self.query()
            .where(ComplianceCaseHistory.compliance_case_id == compliance_case_id)
            .order_by(ComplianceCaseHistory.created_at.asc())
        )
        return list((await self.db.scalars(statement)).all())
