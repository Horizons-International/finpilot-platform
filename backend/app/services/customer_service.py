from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.customer_status_history import CustomerStatusHistory
from app.repositories.customer_repository import CustomerRepository
from app.schemas.customer import (
    CustomerCreate,
    CustomerListResponse,
    CustomerResponse,
    CustomerUpdate,
)
from app.services.audit_service import AuditService
from app.services.customer_audit_log_service import CustomerAuditLogService
from app.utils.audit import serialize_audit_value
from app.utils.constants import DEFAULT_PAGE, DEFAULT_PAGE_SIZE
from app.utils.enums import AuditEventType, CustomerStatus
from app.utils.errors import bad_request, not_found
from app.utils.pagination import validate_pagination


class CustomerService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = CustomerRepository(db)
        self.audit_service = AuditService(db)
        self.customer_audit_service = CustomerAuditLogService(db)

    def create_customer(
        self,
        customer_data: CustomerCreate,
        created_by: UUID,
    ) -> Customer:
        existing_customer = self.repository.get_by_email(
            customer_data.email,
        )

        if existing_customer:
            raise bad_request("Email is already registered.")

        customer = Customer(
            first_name=customer_data.first_name,
            middle_name=customer_data.middle_name,
            last_name=customer_data.last_name,
            date_of_birth=customer_data.date_of_birth,
            nationality=customer_data.nationality,
            country_of_residence=customer_data.country_of_residence,
            email=customer_data.email,
            phone_number=customer_data.phone_number,
            status=CustomerStatus.NEW,
        )

        customer = self.repository.create(customer)

        self.db.flush()

        self.audit_service.log_event(
            event_type=AuditEventType.CUSTOMER_CREATED,
            user_id=created_by,
            resource_type="customer",
            resource_id=customer.id,
        )

        self.db.commit()
        self.db.refresh(customer)

        return customer

    def get_customer(
        self,
        customer_id: UUID,
    ) -> Customer:
        customer = self.repository.get_by_id(customer_id)

        if not customer:
            raise not_found("Customer")

        return customer

    def update_customer(
        self,
        customer_id: UUID,
        customer_data: CustomerUpdate,
        updated_by: UUID,
    ) -> Customer:
        customer = self.get_customer(customer_id)

        update_data = customer_data.model_dump(exclude_unset=True)

        if not update_data:
            raise bad_request("No customer fields were provided for update.")

        if "email" in update_data:
            existing_customer = self.repository.get_by_email(
                update_data["email"],
            )

            if existing_customer and existing_customer.id != customer_id:
                raise bad_request("Email is already registered.")

        changed_fields: list[tuple[str, object | None, object | None]] = []

        for field, new_value in update_data.items():
            old_value = getattr(customer, field)

            if old_value == new_value:
                continue

            changed_fields.append(
                (
                    field,
                    old_value,
                    new_value,
                )
            )

            setattr(
                customer,
                field,
                new_value,
            )

        if not changed_fields:
            raise bad_request("No customer fields were changed.")

        customer = self.repository.update(customer)

        for field, old_value, new_value in changed_fields:
            self.customer_audit_service.create_audit_log(
                customer_id=customer.id,
                user_id=updated_by,
                action="UPDATE",
                changed_field=field,
                old_value=serialize_audit_value(old_value),
                new_value=serialize_audit_value(new_value),
            )

        self.audit_service.log_event(
            event_type=AuditEventType.CUSTOMER_UPDATED,
            user_id=updated_by,
            resource_type="customer",
            resource_id=customer.id,
        )

        self.db.commit()
        self.db.refresh(customer)

        return customer

    def update_status(
        self,
        customer_id: UUID,
        new_status: CustomerStatus,
        changed_by: UUID,
    ) -> Customer:
        customer = self.get_customer(customer_id)

        ALLOWED_STATUS_TRANSITIONS = {
            CustomerStatus.NEW: {
                CustomerStatus.PENDING_VERIFICATION,
                CustomerStatus.REJECTED,
            },
            CustomerStatus.PENDING_VERIFICATION: {
                CustomerStatus.VERIFIED,
                CustomerStatus.REJECTED,
            },
            CustomerStatus.VERIFIED: {
                CustomerStatus.SUSPENDED,
            },
            CustomerStatus.SUSPENDED: {
                CustomerStatus.VERIFIED,
                CustomerStatus.REJECTED,
            },
            CustomerStatus.REJECTED: set(),
        }

        old_status = customer.status

        if new_status not in ALLOWED_STATUS_TRANSITIONS[old_status]:
            raise bad_request(
                f"Invalid status transition: {old_status.value} -> {new_status.value}"
            )

        if old_status == new_status:
            raise bad_request("Customer already has this status.")

        customer.status = new_status

        self.repository.update(customer)

        history = CustomerStatusHistory(
            customer_id=customer.id,
            old_status=old_status,
            new_status=new_status,
            changed_by=changed_by,
            changed_at=datetime.now(timezone.utc),
        )

        self.db.add(history)

        self.audit_service.log_event(
            event_type=AuditEventType.CUSTOMER_STATUS_CHANGED,
            user_id=changed_by,
            resource_type="customer",
            resource_id=customer.id,
        )

        self.db.commit()
        self.db.refresh(customer)

        return customer

    def search_customers(
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
        validate_pagination(
            page,
            page_size,
        )

        try:
            customers, total = self.repository.search(
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

        customer_responses = [
            CustomerResponse.model_validate(customer) for customer in customers
        ]

        total_pages = (total + page_size - 1) // page_size if total > 0 else 0

        return CustomerListResponse(
            customers=customer_responses,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )
