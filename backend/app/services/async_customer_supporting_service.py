"""Native-async customer contact, address, audit and risk-profile use cases."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.customer_address import CustomerAddress
from app.models.customer_audit_log import CustomerAuditLog
from app.models.customer_contact import CustomerContact
from app.models.customer_risk_profile import CustomerRiskProfile
from app.schemas.customer_address import CustomerAddressCreate, CustomerAddressUpdate
from app.schemas.customer_contact import CustomerContactCreate, CustomerContactUpdate
from app.services.async_audit_service import AsyncAuditService
from app.utils.audit import serialize_audit_value
from app.utils.enums import AuditEventType
from app.utils.errors import bad_request, not_found


def _bind_tenant(db: AsyncSession, tenant_id: UUID) -> None:
    active = db.info.get("tenant_id")
    if active is not None and active != tenant_id:
        raise ValueError("The session is already bound to a different tenant.")
    db.info["tenant_id"] = tenant_id


class _CustomerSupportingService:
    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        _bind_tenant(db, tenant_id)
        self.db = db
        self.tenant_id = tenant_id

    async def _require_customer(self, customer_id: UUID) -> Customer:
        customer = await self.db.scalar(
            select(Customer).where(
                Customer.id == customer_id,
                Customer.tenant_id == self.tenant_id,
            )
        )
        if customer is None:
            raise not_found("Customer")
        return customer

    async def _field_audit(
        self,
        *,
        customer_id: UUID,
        actor_id: UUID,
        resource_type: str,
        resource_id: UUID,
        action: str,
        old_value: object | None,
        new_value: object | None,
    ) -> None:
        self.db.add(
            CustomerAuditLog(
                tenant_id=self.tenant_id,
                customer_id=customer_id,
                user_id=actor_id,
                resource_type=resource_type,
                resource_id=resource_id,
                action=action,
                old_value=serialize_audit_value(old_value),
                new_value=serialize_audit_value(new_value),
            )
        )
        await self.db.flush()


class AsyncCustomerContactService(_CustomerSupportingService):
    async def create_contact(
        self, customer_id: UUID, data: CustomerContactCreate, created_by: UUID
    ) -> CustomerContact:
        await self._require_customer(customer_id)
        contact = CustomerContact(
            tenant_id=self.tenant_id,
            customer_id=customer_id,
            **data.model_dump(),
        )
        self.db.add(contact)
        await self.db.flush()
        await self._field_audit(
            customer_id=customer_id,
            actor_id=created_by,
            resource_type="contact",
            resource_id=contact.id,
            action="CREATE CONTACT",
            old_value=None,
            new_value={
                key: serialize_audit_value(getattr(contact, key))
                for key in (
                    "phone_number",
                    "email",
                    "preferred_contact_method",
                    "phone_verified",
                    "email_verified",
                )
            },
        )
        await self.db.commit()
        await self.db.refresh(contact)
        return contact

    async def get_contacts(self, customer_id: UUID) -> list[CustomerContact]:
        await self._require_customer(customer_id)
        result = await self.db.scalars(
            select(CustomerContact)
            .where(
                CustomerContact.tenant_id == self.tenant_id,
                CustomerContact.customer_id == customer_id,
            )
            .order_by(CustomerContact.created_at.asc())
        )
        return list(result.all())

    async def update_contact(
        self,
        customer_id: UUID,
        contact_id: UUID,
        data: CustomerContactUpdate,
        updated_by: UUID,
    ) -> CustomerContact:
        await self._require_customer(customer_id)
        contact = await self.db.scalar(
            select(CustomerContact).where(
                CustomerContact.id == contact_id,
                CustomerContact.customer_id == customer_id,
                CustomerContact.tenant_id == self.tenant_id,
            )
        )
        if contact is None:
            raise not_found("Customer contact")
        changed = []
        for field, value in data.model_dump(exclude_unset=True).items():
            old = getattr(contact, field)
            if old != value:
                changed.append((field, old, value))
                setattr(contact, field, value)
        if not changed:
            return contact
        for field, old, value in changed:
            await self._field_audit(
                customer_id=customer_id,
                actor_id=updated_by,
                resource_type="contact",
                resource_id=contact.id,
                action=f"UPDATE {field.replace('_', ' ').upper()}",
                old_value=old,
                new_value=value,
            )
        await self.db.commit()
        await self.db.refresh(contact)
        return contact


class AsyncCustomerAddressService(_CustomerSupportingService):
    async def _get_primary(self, customer_id: UUID) -> CustomerAddress | None:
        return await self.db.scalar(
            select(CustomerAddress)
            .where(
                CustomerAddress.tenant_id == self.tenant_id,
                CustomerAddress.customer_id == customer_id,
                CustomerAddress.is_primary.is_(True),
            )
            .with_for_update()
        )

    async def _clear_primary(self, address: CustomerAddress, actor_id: UUID) -> None:
        if not address.is_primary:
            return
        address.is_primary = False
        await self._field_audit(
            customer_id=address.customer_id,
            actor_id=actor_id,
            resource_type="address",
            resource_id=address.id,
            action="UPDATE PRIMARY STATUS",
            old_value=True,
            new_value=False,
        )

    async def create_address(
        self, customer_id: UUID, data: CustomerAddressCreate, created_by: UUID
    ) -> CustomerAddress:
        await self._require_customer(customer_id)
        if data.is_primary:
            previous = await self._get_primary(customer_id)
            if previous is not None:
                await self._clear_primary(previous, created_by)
        address = CustomerAddress(
            tenant_id=self.tenant_id,
            customer_id=customer_id,
            **data.model_dump(),
        )
        self.db.add(address)
        await self.db.flush()
        await self._field_audit(
            customer_id=customer_id,
            actor_id=created_by,
            resource_type="address",
            resource_id=address.id,
            action="CREATE ADDRESS",
            old_value=None,
            new_value={
                key: serialize_audit_value(getattr(address, key))
                for key in (
                    "address_line_1",
                    "address_line_2",
                    "city",
                    "state",
                    "country",
                    "postal_code",
                    "address_type",
                    "is_primary",
                )
            },
        )
        await self.db.commit()
        await self.db.refresh(address)
        return address

    async def get_addresses(self, customer_id: UUID) -> list[CustomerAddress]:
        await self._require_customer(customer_id)
        result = await self.db.scalars(
            select(CustomerAddress)
            .where(
                CustomerAddress.tenant_id == self.tenant_id,
                CustomerAddress.customer_id == customer_id,
            )
            .order_by(
                CustomerAddress.is_primary.desc(), CustomerAddress.created_at.asc()
            )
        )
        return list(result.all())

    async def update_address(
        self,
        customer_id: UUID,
        address_id: UUID,
        data: CustomerAddressUpdate,
        updated_by: UUID,
    ) -> CustomerAddress:
        await self._require_customer(customer_id)
        address = await self.db.scalar(
            select(CustomerAddress)
            .where(
                CustomerAddress.id == address_id,
                CustomerAddress.customer_id == customer_id,
                CustomerAddress.tenant_id == self.tenant_id,
            )
            .with_for_update()
        )
        if address is None:
            raise not_found("Customer address")
        changes = data.model_dump(exclude_unset=True)
        if changes.get("is_primary") is True and not address.is_primary:
            previous = await self._get_primary(customer_id)
            if previous is not None and previous.id != address.id:
                await self._clear_primary(previous, updated_by)
        changed = []
        for field, value in changes.items():
            old = getattr(address, field)
            if old != value:
                changed.append((field, old, value))
                setattr(address, field, value)
        if not changed:
            return address
        for field, old, value in changed:
            await self._field_audit(
                customer_id=customer_id,
                actor_id=updated_by,
                resource_type="address",
                resource_id=address.id,
                action=f"UPDATE {field.replace('_', ' ').upper()}",
                old_value=old,
                new_value=value,
            )
        await self.db.commit()
        await self.db.refresh(address)
        return address

    async def set_primary(
        self, customer_id: UUID, address_id: UUID, updated_by: UUID
    ) -> CustomerAddress:
        await self._require_customer(customer_id)
        address = await self.db.scalar(
            select(CustomerAddress)
            .where(
                CustomerAddress.id == address_id,
                CustomerAddress.customer_id == customer_id,
                CustomerAddress.tenant_id == self.tenant_id,
            )
            .with_for_update()
        )
        if address is None:
            raise not_found("Customer address")
        if address.is_primary:
            return address

        previous = await self._get_primary(customer_id)
        if previous is not None and previous.id != address.id:
            previous.is_primary = False
            await self._field_audit(
                customer_id=customer_id,
                actor_id=updated_by,
                resource_type="address",
                resource_id=previous.id,
                action="UPDATE PRIMARY STATUS",
                old_value=True,
                new_value=False,
            )

        address.is_primary = True
        await self._field_audit(
            customer_id=customer_id,
            actor_id=updated_by,
            resource_type="address",
            resource_id=address.id,
            action="SET PRIMARY ADDRESS",
            old_value=False,
            new_value=True,
        )
        await self.db.commit()
        await self.db.refresh(address)
        return address


class AsyncCustomerAuditLogService(_CustomerSupportingService):
    async def get_customer_history(self, customer_id: UUID) -> list[CustomerAuditLog]:
        await self._require_customer(customer_id)
        result = await self.db.scalars(
            select(CustomerAuditLog)
            .where(
                CustomerAuditLog.tenant_id == self.tenant_id,
                CustomerAuditLog.customer_id == customer_id,
            )
            .order_by(CustomerAuditLog.created_at.desc())
        )
        return list(result.all())


class AsyncCustomerRiskProfileService(_CustomerSupportingService):
    async def create_profile(
        self,
        *,
        customer_id: UUID,
        risk_level,
        risk_score: int,
        risk_category: str,
        assessed_at,
        assessment_source: str,
        user_id: UUID,
        email: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> CustomerRiskProfile:
        await self._require_customer(customer_id)
        existing = await self.db.scalar(
            select(CustomerRiskProfile.id).where(
                CustomerRiskProfile.tenant_id == self.tenant_id,
                CustomerRiskProfile.customer_id == customer_id,
            )
        )
        if existing is not None:
            raise bad_request("A risk profile already exists for this customer.")
        profile = CustomerRiskProfile(
            tenant_id=self.tenant_id,
            customer_id=customer_id,
            risk_level=risk_level,
            risk_score=risk_score,
            risk_category=risk_category,
            assessed_at=assessed_at,
            assessment_source=assessment_source,
        )
        self.db.add(profile)
        try:
            await self.db.flush()
        except IntegrityError as exc:
            await self.db.rollback()
            raise bad_request(
                "A risk profile already exists for this customer."
            ) from exc
        await AsyncAuditService(self.db).log_event(
            event_type=AuditEventType.CUSTOMER_RISK_PROFILE_CREATED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="customer_risk_profile",
            resource_id=profile.id,
        )
        await self.db.commit()
        await self.db.refresh(profile)

        return profile

    async def get_by_id(self, profile_id: UUID) -> CustomerRiskProfile:
        profile = await self.db.scalar(
            select(CustomerRiskProfile).where(
                CustomerRiskProfile.id == profile_id,
                CustomerRiskProfile.tenant_id == self.tenant_id,
            )
        )
        if profile is None:
            raise not_found("Customer risk profile")
        return profile

    async def get_by_customer_id(self, customer_id: UUID) -> CustomerRiskProfile:
        await self._require_customer(customer_id)
        profile = await self.db.scalar(
            select(CustomerRiskProfile).where(
                CustomerRiskProfile.customer_id == customer_id,
                CustomerRiskProfile.tenant_id == self.tenant_id,
            )
        )
        if profile is None:
            raise not_found("Customer risk profile")
        return profile

    async def get_all(self) -> list[CustomerRiskProfile]:
        result = await self.db.scalars(
            select(CustomerRiskProfile)
            .where(CustomerRiskProfile.tenant_id == self.tenant_id)
            .order_by(CustomerRiskProfile.assessed_at.desc())
        )
        return list(result.all())
