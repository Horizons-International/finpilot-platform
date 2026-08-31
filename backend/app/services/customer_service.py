from uuid import UUID

from sqlalchemy.orm import Session

from app.models.audit_log import AuditEventType
from app.models.customer import Customer, CustomerStatus
from app.repositories.customer_repository import CustomerRepository
from app.schemas.customer import (
    CustomerCreate,
    CustomerUpdate,
)
from app.services.audit_service import AuditService
from app.utils.errors import bad_request, not_found


class CustomerService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = CustomerRepository(db)
        self.audit_service = AuditService(db)

    def create_customer(
        self,
        customer_data: CustomerCreate,
        user_id: UUID,
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
            status=CustomerStatus.ACTIVE,
        )

        customer = self.repository.create(customer)

        self.db.flush()

        self.audit_service.log_event(
            event_type=AuditEventType.CUSTOMER_CREATED,
            user_id=user_id,
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
        user_id: UUID,
    ) -> Customer:
        customer = self.get_customer(customer_id)

        if customer_data.email is not None:
            existing_customer = self.repository.get_by_email(
                customer_data.email,
            )

            if existing_customer and existing_customer.id != customer_id:
                raise bad_request("Email is already registered.")

            customer.email = customer_data.email

        if customer_data.first_name is not None:
            customer.first_name = customer_data.first_name

        if customer_data.middle_name is not None:
            customer.middle_name = customer_data.middle_name

        if customer_data.last_name is not None:
            customer.last_name = customer_data.last_name

        if customer_data.date_of_birth is not None:
            customer.date_of_birth = customer_data.date_of_birth

        if customer_data.nationality is not None:
            customer.nationality = customer_data.nationality

        if customer_data.country_of_residence is not None:
            customer.country_of_residence = customer_data.country_of_residence

        if customer_data.phone_number is not None:
            customer.phone_number = customer_data.phone_number

        if customer_data.status is not None:
            customer.status = customer_data.status

        customer = self.repository.update(customer)

        self.audit_service.log_event(
            event_type=AuditEventType.CUSTOMER_UPDATED,
            user_id=user_id,
            resource_type="customer",
            resource_id=customer.id,
        )

        self.db.commit()
        self.db.refresh(customer)

        return customer
