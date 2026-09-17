from uuid import UUID

from sqlalchemy.orm import Session, selectinload

from app.models.customer import Customer
from app.models.document import CustomerDocument
from app.models.verification_case import IdentityVerificationCase


class ComplianceContextRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_customer(
        self,
        customer_id: UUID,
    ) -> Customer | None:
        return (
            self.db.query(Customer)
            .options(
                selectinload(Customer.addresses),
                selectinload(Customer.contacts),
                selectinload(Customer.verification_cases)
                .selectinload(IdentityVerificationCase.documents)
                .selectinload(CustomerDocument.ocr_results),
                selectinload(Customer.verification_cases).selectinload(
                    IdentityVerificationCase.reviews
                ),
            )
            .filter(Customer.id == customer_id)
            .first()
        )

    def get_verification_case(
        self,
        case_id: UUID,
    ) -> IdentityVerificationCase | None:
        return (
            self.db.query(IdentityVerificationCase)
            .options(
                selectinload(IdentityVerificationCase.customer),
                selectinload(IdentityVerificationCase.documents).selectinload(
                    CustomerDocument.ocr_results
                ),
                selectinload(IdentityVerificationCase.documents).selectinload(
                    CustomerDocument.document_type
                ),
                selectinload(IdentityVerificationCase.reviews),
            )
            .filter(IdentityVerificationCase.id == case_id)
            .first()
        )

    def get_document(
        self,
        document_id: UUID,
    ) -> CustomerDocument | None:
        return (
            self.db.query(CustomerDocument)
            .options(
                selectinload(CustomerDocument.customer),
                selectinload(CustomerDocument.verification_case),
                selectinload(CustomerDocument.document_type),
                selectinload(CustomerDocument.ocr_results),
            )
            .filter(CustomerDocument.id == document_id)
            .first()
        )
