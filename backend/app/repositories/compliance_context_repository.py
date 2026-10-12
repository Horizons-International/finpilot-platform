from uuid import UUID

from sqlalchemy.orm import Session, selectinload, with_loader_criteria

from app.models.customer import Customer
from app.models.customer_address import CustomerAddress
from app.models.customer_contact import CustomerContact
from app.models.document import CustomerDocument
from app.models.ocr_result import OCRResult
from app.models.verification_case import IdentityVerificationCase
from app.models.verification_review import VerificationReview


class ComplianceContextRepository:
    def __init__(self, db: Session, tenant_id: UUID | None = None) -> None:
        resolved_tenant_id = (
            tenant_id if tenant_id is not None else db.info.get("tenant_id")
        )
        if not isinstance(resolved_tenant_id, UUID):
            raise ValueError(
                "A tenant context is required for compliance context queries."
            )

        self.db = db
        self.tenant_id = resolved_tenant_id

    def _tenant_loader_options(self) -> tuple:
        tenant_id = self.tenant_id
        return (
            with_loader_criteria(
                Customer,
                lambda model: model.tenant_id == tenant_id,
                include_aliases=True,
            ),
            with_loader_criteria(
                CustomerAddress,
                lambda model: model.tenant_id == tenant_id,
                include_aliases=True,
            ),
            with_loader_criteria(
                CustomerContact,
                lambda model: model.tenant_id == tenant_id,
                include_aliases=True,
            ),
            with_loader_criteria(
                CustomerDocument,
                lambda model: model.tenant_id == tenant_id,
                include_aliases=True,
            ),
            with_loader_criteria(
                IdentityVerificationCase,
                lambda model: model.tenant_id == tenant_id,
                include_aliases=True,
            ),
            with_loader_criteria(
                OCRResult,
                lambda model: model.tenant_id == tenant_id,
                include_aliases=True,
            ),
            with_loader_criteria(
                VerificationReview,
                lambda model: model.tenant_id == tenant_id,
                include_aliases=True,
            ),
        )

    def get_customer(self, customer_id: UUID) -> Customer | None:
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
                *self._tenant_loader_options(),
            )
            .filter(
                Customer.id == customer_id,
                Customer.tenant_id == self.tenant_id,
            )
            .first()
        )

    def get_verification_case(self, case_id: UUID) -> IdentityVerificationCase | None:
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
                *self._tenant_loader_options(),
            )
            .filter(
                IdentityVerificationCase.id == case_id,
                IdentityVerificationCase.tenant_id == self.tenant_id,
            )
            .first()
        )

    def get_document(self, document_id: UUID) -> CustomerDocument | None:
        return (
            self.db.query(CustomerDocument)
            .options(
                selectinload(CustomerDocument.customer),
                selectinload(CustomerDocument.verification_case),
                selectinload(CustomerDocument.document_type),
                selectinload(CustomerDocument.ocr_results),
                *self._tenant_loader_options(),
            )
            .filter(
                CustomerDocument.id == document_id,
                CustomerDocument.tenant_id == self.tenant_id,
            )
            .first()
        )
