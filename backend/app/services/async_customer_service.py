"""Async customer lifecycle service."""

from datetime import datetime, timezone
from typing import Any, NoReturn
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.customer_audit_log import CustomerAuditLog
from app.models.customer_status_history import CustomerStatusHistory
from app.repositories.async_customer_repository import AsyncCustomerRepository
from app.schemas.customer import (
    CustomerCreate,
    CustomerListResponse,
    CustomerResponse,
    CustomerUpdate,
)
from app.services.async_audit_service import AsyncAuditService
from app.utils.audit import serialize_audit_value
from app.utils.constants import DEFAULT_PAGE, DEFAULT_PAGE_SIZE
from app.utils.enums import AuditEventType, CustomerStatus
from app.utils.errors import bad_request, not_found
from app.utils.pagination import validate_pagination

ALLOWED_STATUS_TRANSITIONS = {
    CustomerStatus.NEW: {CustomerStatus.PENDING_VERIFICATION, CustomerStatus.REJECTED},
    CustomerStatus.PENDING_VERIFICATION: {
        CustomerStatus.VERIFIED,
        CustomerStatus.REJECTED,
    },
    CustomerStatus.VERIFIED: {CustomerStatus.SUSPENDED},
    CustomerStatus.SUSPENDED: {CustomerStatus.VERIFIED, CustomerStatus.REJECTED},
    CustomerStatus.REJECTED: set(),
}


class AsyncCustomerService:
    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.db.info["tenant_id"] = tenant_id
        self.repository = AsyncCustomerRepository(db, tenant_id)
        self.audit_service = AsyncAuditService(db)

    async def _deny_access(self, customer_id: UUID) -> NoReturn:
        await self.audit_service.log_access_denied(
            resource_type="customer",
            resource_id=customer_id,
            user_id=self.db.info.get("tenant_user_id"),
            email=self.db.info.get("tenant_user_email"),
            ip_address=self.db.info.get("tenant_ip_address"),
            user_agent=self.db.info.get("tenant_user_agent"),
        )
        raise not_found("Customer")

    async def _field_audit(
        self,
        *,
        customer_id: UUID,
        user_id: UUID,
        action: str,
        old_value: object | None,
        new_value: object | None,
        resource_type: str = "customer",
        resource_id: UUID | None = None,
    ) -> None:
        self.db.add(
            CustomerAuditLog(
                tenant_id=self.tenant_id,
                customer_id=customer_id,
                user_id=user_id,
                resource_type=resource_type,
                resource_id=resource_id or customer_id,
                action=action,
                old_value=serialize_audit_value(old_value),
                new_value=serialize_audit_value(new_value),
            )
        )
        await self.db.flush()

    async def _enqueue_webhook(self, event_type: str, data: dict[str, Any]) -> None:
        # This existing helper is synchronous ORM code. run_sync adapts its SQL
        # operations to the AsyncSession's connection without blocking the loop.
        from app.webhooks.events import enqueue_webhook_event

        await self.db.run_sync(
            lambda sync_db: enqueue_webhook_event(
                sync_db,
                tenant_id=self.tenant_id,
                event_type=event_type,
                data=data,
            )
        )

    async def create_customer(
        self,
        customer_data: CustomerCreate,
        created_by: UUID,
        email: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> Customer:
        existing = await self.repository.get_by_email(str(customer_data.email))
        if existing is not None:
            raise bad_request("Email is already registered.")

        customer = Customer(
            tenant_id=self.tenant_id,
            first_name=customer_data.first_name,
            middle_name=customer_data.middle_name,
            last_name=customer_data.last_name,
            date_of_birth=customer_data.date_of_birth,
            nationality=customer_data.nationality,
            country_of_residence=customer_data.country_of_residence,
            email=str(customer_data.email),
            phone_number=customer_data.phone_number,
            status=CustomerStatus.NEW,
        )
        customer = await self.repository.create(customer)
        await self.audit_service.log_event(
            event_type=AuditEventType.CUSTOMER_CREATED,
            user_id=created_by,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="customer",
            resource_id=customer.id,
        )
        await self._field_audit(
            customer_id=customer.id,
            user_id=created_by,
            action="CREATE CUSTOMER",
            old_value=None,
            new_value={
                "first_name": serialize_audit_value(customer.first_name),
                "middle_name": serialize_audit_value(customer.middle_name),
                "last_name": serialize_audit_value(customer.last_name),
                "date_of_birth": serialize_audit_value(customer.date_of_birth),
                "nationality": serialize_audit_value(customer.nationality),
                "country_of_residence": serialize_audit_value(
                    customer.country_of_residence
                ),
                "email": serialize_audit_value(customer.email),
                "phone_number": serialize_audit_value(customer.phone_number),
                "status": serialize_audit_value(customer.status),
            },
        )
        await self._enqueue_webhook(
            "customer.created",
            {"customer_id": str(customer.id), "status": customer.status.value},
        )
        await self.db.commit()
        await self.db.refresh(customer)
        return customer

    async def get_customer(self, customer_id: UUID) -> Customer:
        customer = await self.repository.get_by_id(customer_id)
        if customer is None:
            await self._deny_access(customer_id)
        return customer

    async def update_customer(
        self,
        customer_id: UUID,
        customer_data: CustomerUpdate,
        updated_by: UUID,
        *,
        email: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        commit: bool = True,
    ) -> Customer:
        customer = await self.get_customer(customer_id)
        update_data = customer_data.model_dump(exclude_unset=True)
        if not update_data:
            raise bad_request("No customer fields were provided for update.")

        changed_fields: list[tuple[str, object | None, object | None]] = []
        for field, new_value in update_data.items():
            old_value = getattr(customer, field)
            if old_value != new_value:
                changed_fields.append((field, old_value, new_value))
        if not changed_fields:
            raise bad_request("No customer fields were changed.")

        changed_field_names = {field for field, _, _ in changed_fields}
        if "email" in changed_field_names:
            new_email = update_data["email"]
            existing = await self.repository.get_by_email(
                str(new_email) if new_email else None
            )
            if existing is not None and existing.id != customer_id:
                raise bad_request("Email is already registered.")

        for field, _, new_value in changed_fields:
            setattr(customer, field, new_value)
        customer = await self.repository.update(customer)
        for field, old_value, new_value in changed_fields:
            await self._field_audit(
                customer_id=customer.id,
                user_id=updated_by,
                action=f"UPDATE {field.replace('_', ' ').upper()}",
                old_value=old_value,
                new_value=new_value,
            )
        await self.audit_service.log_event(
            event_type=AuditEventType.CUSTOMER_UPDATED,
            user_id=updated_by,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="customer",
            resource_id=customer.id,
        )
        await self._enqueue_webhook(
            "customer.updated",
            {
                "customer_id": str(customer.id),
                "status": customer.status.value,
                "changed_fields": sorted(changed_field_names),
            },
        )
        if commit:
            await self.db.commit()
        await self.db.refresh(customer)
        return customer

    async def update_status(
        self,
        customer_id: UUID,
        new_status: CustomerStatus,
        changed_by: UUID,
        email: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> Customer:
        customer = await self.get_customer(customer_id)
        old_status = customer.status
        if old_status == new_status:
            raise bad_request("Customer already has this status.")
        if new_status not in ALLOWED_STATUS_TRANSITIONS[old_status]:
            raise bad_request(
                f"Invalid status transition: {old_status.value} -> {new_status.value}"
            )
        customer.status = new_status
        customer = await self.repository.update(customer)
        self.db.add(
            CustomerStatusHistory(
                tenant_id=self.tenant_id,
                customer_id=customer.id,
                old_status=old_status,
                new_status=new_status,
                changed_by=changed_by,
                changed_at=datetime.now(timezone.utc),
            )
        )
        await self.audit_service.log_event(
            event_type=AuditEventType.CUSTOMER_STATUS_CHANGED,
            user_id=changed_by,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="customer",
            resource_id=customer.id,
        )
        await self._field_audit(
            customer_id=customer.id,
            user_id=changed_by,
            action="UPDATE STATUS",
            old_value={"status": old_status.value},
            new_value={"status": new_status.value},
        )
        await self._enqueue_webhook(
            "customer.updated",
            {
                "customer_id": str(customer.id),
                "status": customer.status.value,
                "changed_fields": ["status"],
            },
        )
        await self.db.commit()
        await self.db.refresh(customer)
        return customer

    async def search_customers(
        self,
        customer_id: UUID | None = None,
        name: str | None = None,
        phone_number: str | None = None,
        email: str | None = None,
        status: CustomerStatus | None = None,
        page: int = DEFAULT_PAGE,
        page_size: int = DEFAULT_PAGE_SIZE,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> CustomerListResponse:
        validate_pagination(page, page_size)
        try:
            customers, total = await self.repository.search(
                customer_id=customer_id,
                name=name,
                phone_number=phone_number,
                email=email,
                status=status,
                page=page,
                page_size=page_size,
                sort_by=sort_by,
                sort_order=sort_order,
            )
        except ValueError as exc:
            raise bad_request(str(exc)) from exc
        pages = (total + page_size - 1) // page_size if total > 0 else 0
        return CustomerListResponse(
            customers=[CustomerResponse.model_validate(item) for item in customers],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=pages,
        )
