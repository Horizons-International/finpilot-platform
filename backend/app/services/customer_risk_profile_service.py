from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.customer_risk_profile import CustomerRiskProfile
from app.repositories.customer_repository import CustomerRepository
from app.repositories.customer_risk_profile_repository import (
    CustomerRiskProfileRepository,
)
from app.services.audit_service import AuditService
from app.utils.enums import AuditEventType
from app.utils.errors import bad_request, not_found


class CustomerRiskProfileService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = CustomerRiskProfileRepository(db)
        self.customer_repository = CustomerRepository(db)
        self.audit_service = AuditService(db)

    def create_profile(
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
        customer = self.customer_repository.get_by_id(customer_id)

        if customer is None:
            raise not_found("Customer")

        existing_profile = self.repository.get_by_customer_id(customer_id)

        if existing_profile is not None:
            raise bad_request("A risk profile already exists for this customer.")

        profile = CustomerRiskProfile(
            customer_id=customer_id,
            risk_level=risk_level,
            risk_score=risk_score,
            risk_category=risk_category,
            assessed_at=assessed_at,
            assessment_source=assessment_source,
        )

        self.db.add(profile)

        try:
            self.db.flush()
        except IntegrityError:
            self.db.rollback()
            raise bad_request("A risk profile already exists for this customer.")

        self.audit_service.log_event(
            event_type=AuditEventType.CUSTOMER_RISK_PROFILE_CREATED,
            user_id=user_id,
            email=email,
            resource_type="customer_risk_profile",
            resource_id=profile.id,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        self.db.commit()
        self.db.refresh(profile)

        return profile

    def get_by_id(
        self,
        profile_id: UUID,
    ) -> CustomerRiskProfile:
        profile = self.repository.get_by_id(profile_id)

        if profile is None:
            raise not_found("Customer risk profile")

        return profile

    def get_by_customer_id(
        self,
        customer_id: UUID,
    ) -> CustomerRiskProfile:
        profile = self.repository.get_by_customer_id(customer_id)

        if profile is None:
            raise not_found("Customer risk profile")

        return profile

    def get_all(self) -> list[CustomerRiskProfile]:
        return self.repository.get_all()
