"""Tenant-scoped async persistence for identity verification cases."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.user import User
from app.models.verification_case import IdentityVerificationCase
from app.repositories.async_tenant_scoped_repository import (
    AsyncTenantScopedRepository,
)
from app.utils.enums import VerificationStatus, VerificationType


class AsyncVerificationCaseRepository(
    AsyncTenantScopedRepository[IdentityVerificationCase]
):
    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        super().__init__(db=db, model=IdentityVerificationCase, tenant_id=tenant_id)

    async def _validate_related_ownership(self, case: IdentityVerificationCase) -> None:
        customer_id = await self.db.scalar(
            select(Customer.id).where(
                Customer.id == case.customer_id,
                Customer.tenant_id == self.tenant_id,
            )
        )
        if customer_id is None:
            raise ValueError("Verification case customer is outside this tenant.")
        for user_id, label in (
            (case.assigned_to, "assigned reviewer"),
            (case.assigned_by, "assigning user"),
        ):
            if user_id is not None:
                exists = await self.db.scalar(
                    select(User.id).where(
                        User.id == user_id,
                        User.tenant_id == self.tenant_id,
                    )
                )
                if exists is None:
                    raise ValueError(
                        f"Verification case {label} is outside this tenant."
                    )

    async def create(
        self, entity: IdentityVerificationCase
    ) -> IdentityVerificationCase:
        await self._validate_related_ownership(entity)
        return await super().create(entity)

    async def update(
        self, entity: IdentityVerificationCase
    ) -> IdentityVerificationCase:
        if entity.tenant_id != self.tenant_id:
            raise ValueError(
                "Cannot update a verification case owned by another tenant."
            )
        await self._validate_related_ownership(entity)
        return await super().update(entity)

    async def get_by_customer_id(
        self, customer_id: UUID
    ) -> list[IdentityVerificationCase]:
        statement = (
            self.query()
            .where(IdentityVerificationCase.customer_id == customer_id)
            .order_by(IdentityVerificationCase.created_at.desc())
        )
        return list((await self.db.scalars(statement)).all())

    async def get_active_by_customer_and_type(
        self,
        customer_id: UUID,
        verification_type: VerificationType,
    ) -> IdentityVerificationCase | None:
        statement = self.query().where(
            IdentityVerificationCase.customer_id == customer_id,
            IdentityVerificationCase.verification_type == verification_type,
            IdentityVerificationCase.status.in_(
                {
                    VerificationStatus.NOT_STARTED,
                    VerificationStatus.PENDING,
                    VerificationStatus.UNDER_REVIEW,
                }
            ),
        )
        return await self.db.scalar(statement)

    async def get_by_id_and_customer(
        self, verification_case_id: UUID, customer_id: UUID
    ) -> IdentityVerificationCase | None:
        return await self.db.scalar(
            self.query().where(
                IdentityVerificationCase.id == verification_case_id,
                IdentityVerificationCase.customer_id == customer_id,
            )
        )

    async def get_by_id_and_customer_and_reviewer(
        self,
        verification_case_id: UUID,
        customer_id: UUID,
        reviewer_id: UUID,
    ) -> IdentityVerificationCase | None:
        return await self.db.scalar(
            self.query().where(
                IdentityVerificationCase.id == verification_case_id,
                IdentityVerificationCase.customer_id == customer_id,
                IdentityVerificationCase.assigned_to == reviewer_id,
            )
        )
